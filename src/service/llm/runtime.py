"""Process-local OpenAI SDK clients and model execution state."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from threading import Lock

from openai import AsyncOpenAI

from .config import LLMConfig, ModelCapabilities
from .exceptions import LLMConfigurationError
from .models import StructuredOutputMode

type OpenAIClientFactory = Callable[..., AsyncOpenAI]


class _EffectiveStructuredMode:
    """Alias-local compare-and-set cache for provider-supported output modes."""

    __slots__ = ("_index", "_lock", "_modes")

    def __init__(self, modes: tuple[StructuredOutputMode, ...]) -> None:
        self._modes = modes
        self._index = 0
        self._lock = Lock()

    def current(self) -> StructuredOutputMode:
        with self._lock:
            if not self._modes:
                raise RuntimeError("model has no configured structured-output mode")
            return self._modes[self._index]

    def downgrade(self, expected: StructuredOutputMode) -> StructuredOutputMode:
        """Advance only if *expected* is still current, then return current mode."""
        with self._lock:
            if not self._modes:
                raise RuntimeError("model has no configured structured-output mode")
            current = self._modes[self._index]
            if current == expected and self._index + 1 < len(self._modes):
                self._index += 1
            return self._modes[self._index]


@dataclass(frozen=True, slots=True)
class ModelHandle:
    """Immutable model snapshot with shared endpoint and alias-local state."""

    alias: str
    endpoint_alias: str
    model_id: str
    capabilities: ModelCapabilities
    client: AsyncOpenAI
    semaphore: asyncio.Semaphore
    _structured_mode: _EffectiveStructuredMode = field(repr=False, compare=False)

    def effective_structured_mode(self) -> StructuredOutputMode:
        return self._structured_mode.current()

    def downgrade_structured_mode(
        self, expected: StructuredOutputMode
    ) -> StructuredOutputMode:
        return self._structured_mode.downgrade(expected)


class LLMRuntime:
    """Own shared endpoint SDK clients and immutable model handles."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        client_factory: OpenAIClientFactory = AsyncOpenAI,
    ) -> None:
        self._clients = {
            alias: client_factory(
                api_key=endpoint.api_key.get_secret_value(),
                base_url=str(endpoint.base_url),
                timeout=float(endpoint.timeout_seconds),
                max_retries=int(endpoint.max_retries),
            )
            for alias, endpoint in config.endpoints.items()
        }
        self._handles = {
            alias: ModelHandle(
                alias=alias,
                endpoint_alias=model.endpoint,
                model_id=model.model,
                capabilities=model.capabilities,
                client=self._clients[model.endpoint],
                semaphore=asyncio.Semaphore(model.max_concurrent),
                _structured_mode=_EffectiveStructuredMode(
                    model.capabilities.structured_output_modes
                ),
            )
            for alias, model in config.models.items()
        }
        self._lifecycle_lock = Lock()
        self._close_task: asyncio.Task[None] | None = None
        self._closing = False
        self._active_calls = 0
        self._drained = asyncio.Event()
        self._drained.set()

    def resolve(self, alias: str) -> ModelHandle:
        """Resolve one explicit configured model alias."""
        with self._lifecycle_lock:
            return self._resolve_locked(alias)

    @asynccontextmanager
    async def lease(self, alias: str) -> AsyncIterator[ModelHandle]:
        """Atomically accept one explicit model call until it finishes."""
        with self._lifecycle_lock:
            handle = self._resolve_locked(alias)
            self._active_calls += 1
            if self._active_calls == 1:
                self._drained.clear()
        try:
            yield handle
        finally:
            with self._lifecycle_lock:
                self._active_calls -= 1
                if self._active_calls == 0:
                    self._drained.set()

    def _resolve_locked(self, alias: str) -> ModelHandle:
        if self._closing:
            raise LLMConfigurationError(model_alias=alias)
        handle = self._handles.get(alias)
        if handle is None:
            raise LLMConfigurationError(model_alias=alias)
        return handle

    async def aclose(self) -> None:
        """Close every endpoint client exactly once, safely under concurrency."""
        with self._lifecycle_lock:
            task = self._close_task
            if task is None:
                self._closing = True
                task = asyncio.create_task(self._drain_and_close_clients())
                self._close_task = task
        await asyncio.shield(task)

    async def _drain_and_close_clients(self) -> None:
        await self._drained.wait()
        results = await asyncio.gather(
            *(client.close() for client in self._clients.values()),
            return_exceptions=True,
        )
        if any(isinstance(result, BaseException) for result in results):
            raise RuntimeError("one or more LLM endpoint clients failed to close")
