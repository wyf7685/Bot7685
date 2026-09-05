"""Endpoint backends, alias-local execution policy, and runtime leases."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from threading import Lock
from time import perf_counter
from typing import Self

from ._adapters import create_backend
from ._backend import (
    BackendError,
    CompletionReply,
    CompletionRequest,
    CompletionStop,
    EndpointBackend,
    ModelTurn,
    UnsupportedStructuredMode,
    UserTurn,
)
from .config import AnthropicThinkingConfig, EndpointProtocol, LLMConfig
from .exceptions import (
    LLMCapabilityError,
    LLMConfigurationError,
    LLMErrorCategory,
    LLMRunError,
)
from .models import (
    ChatInputPart,
    ImagePart,
    ModelCallTrace,
    ModelCapabilities,
    ModelCapability,
    StructuredOutputMode,
)


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
class _ModelHandle:
    """Immutable model policy sharing one stateless endpoint backend."""

    alias: str
    model_id: str
    capabilities: ModelCapabilities
    protocol: EndpointProtocol
    backend: EndpointBackend = field(repr=False, compare=False)
    semaphore: asyncio.Semaphore = field(repr=False, compare=False)
    _structured_mode: _EffectiveStructuredMode = field(repr=False, compare=False)
    default_max_output_tokens: int | None = None
    anthropic_thinking: AnthropicThinkingConfig | None = None

    def require_capability(self, capability: ModelCapability) -> Self:
        self.capabilities.require(capability, model_alias=self.alias)
        return self

    def effective_structured_mode(self) -> StructuredOutputMode:
        return self._structured_mode.current()

    def downgrade_structured_mode(
        self, expected: StructuredOutputMode
    ) -> StructuredOutputMode:
        return self._structured_mode.downgrade(expected)

    def _validate_images(self, parts: tuple[ChatInputPart, ...]) -> None:
        for part in parts:
            if isinstance(part, ImagePart):
                self.require_capability(ModelCapability.VISION)
                if (
                    self.protocol is EndpointProtocol.ANTHROPIC_MESSAGES
                    and part.detail != "auto"
                ):
                    raise LLMCapabilityError(
                        model_alias=self.alias,
                        capability=ModelCapability.VISION,
                    )

    def _prepare_request(self, request: CompletionRequest) -> CompletionRequest:
        self._validate_images(request.prompt.parts)
        for item in request.history:
            if isinstance(item, UserTurn):
                self._validate_images(item.parts)
        if request.tools:
            self.require_capability(ModelCapability.TOOLS)
            if request.parallel_tool_calls:
                self.require_capability(ModelCapability.PARALLEL_TOOL_CALLS)
        if request.temperature is not None:
            self.require_capability(ModelCapability.TEMPERATURE)
        if request.structured is not None:
            self.require_capability(ModelCapability.STRUCTURED_OUTPUT)
        try:
            effort = self.capabilities.resolve_reasoning_effort(
                request.reasoning_effort
            )
        except ValueError as error:
            raise LLMCapabilityError(
                model_alias=self.alias,
                capability=ModelCapability.REASONING_EFFORT,
                cause=error,
            ) from None

        maximum = (
            request.max_output_tokens
            if request.max_output_tokens is not None
            else self.default_max_output_tokens
        )
        thinking = self.anthropic_thinking
        if self.protocol is EndpointProtocol.ANTHROPIC_MESSAGES and effort == "none":
            thinking = AnthropicThinkingConfig(type="disabled")
        if thinking is not None and thinking.type != "disabled":
            if request.temperature is not None and request.temperature != 1:
                raise LLMCapabilityError(
                    model_alias=self.alias,
                    capability=ModelCapability.TEMPERATURE,
                )
            if thinking.type == "enabled" and (
                maximum is None
                or thinking.budget_tokens is None
                or thinking.budget_tokens >= maximum
            ):
                raise LLMRunError(
                    category=LLMErrorCategory.LIMITS,
                    model_alias=self.alias,
                )
        return replace(
            request,
            reasoning_effort=effort,
            max_output_tokens=maximum,
            thinking=thinking,
        )

    async def complete(self, request: CompletionRequest) -> ModelTurn:
        request = self._prepare_request(request)
        started = perf_counter()
        async with self.semaphore:
            try:
                reply = await self.backend.complete(self.model_id, request)
            except UnsupportedStructuredMode:
                raise
            except BackendError as error:
                cause = error.cause or error
                if error.category is LLMErrorCategory.CONFIGURATION:
                    raise LLMConfigurationError(
                        model_alias=self.alias, cause=cause
                    ) from None
                if error.category is LLMErrorCategory.CAPABILITY:
                    raise LLMCapabilityError(
                        model_alias=self.alias,
                        capability=ModelCapability.VISION,
                        cause=cause,
                    ) from None
                raise LLMRunError(
                    category=error.category,
                    model_alias=self.alias,
                    cause=cause,
                ) from None

        if not isinstance(reply, CompletionReply):
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE, model_alias=self.alias
            )
        if reply.stop is CompletionStop.LENGTH:
            raise LLMRunError(category=LLMErrorCategory.LIMITS, model_alias=self.alias)
        if reply.stop in {CompletionStop.REFUSAL, CompletionStop.FAILED}:
            raise LLMRunError(
                category=LLMErrorCategory.PROVIDER, model_alias=self.alias
            )
        if (
            reply.stop is CompletionStop.COMPLETE
            and (reply.content is None or not reply.content.strip())
        ) or (reply.stop is CompletionStop.TOOL_CALLS and not request.tools):
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE, model_alias=self.alias
            )
        return ModelTurn(
            reply=reply,
            trace=ModelCallTrace(
                model_alias=self.alias,
                model_id=self.model_id,
                usage=reply.usage,
                elapsed=perf_counter() - started,
                finish_reason=reply.finish_reason,
                reasoning_effort=request.reasoning_effort,
                structured_mode=(
                    request.structured.mode if request.structured is not None else None
                ),
            ),
        )


class LLMRuntime:
    """Own endpoint backends and immutable model handles until leases drain."""

    def __init__(self, config: LLMConfig) -> None:
        # Backends allocate clients lazily; snapshot construction owns no I/O resources.
        self._backends = {
            alias: create_backend(endpoint)
            for alias, endpoint in config.endpoints.items()
        }
        self._handles = {
            alias: _ModelHandle(
                alias=alias,
                model_id=model.model,
                capabilities=model.capabilities,
                protocol=config.endpoints[model.endpoint].protocol,
                backend=self._backends[model.endpoint],
                semaphore=asyncio.Semaphore(model.max_concurrent),
                _structured_mode=_EffectiveStructuredMode(
                    model.capabilities.structured_output_modes
                ),
                default_max_output_tokens=model.default_max_output_tokens,
                anthropic_thinking=model.anthropic_thinking,
            )
            for alias, model in config.models.items()
        }
        self._lifecycle_lock = Lock()
        self._close_task: asyncio.Task[None] | None = None
        self._closing = False
        self._active_calls = 0
        self._drained = asyncio.Event()
        self._drained.set()

    def resolve(self, alias: str) -> _ModelHandle:
        """Resolve one explicit configured model alias."""
        with self._lifecycle_lock:
            return self._resolve_locked(alias)

    @asynccontextmanager
    async def lease(self, alias: str) -> AsyncIterator[_ModelHandle]:
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

    def _resolve_locked(self, alias: str) -> _ModelHandle:
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
            *(backend.aclose() for backend in self._backends.values()),
            return_exceptions=True,
        )
        if exceptions := [
            result for result in results if isinstance(result, BaseException)
        ]:
            raise BaseExceptionGroup(
                "one or more LLM endpoint clients failed to close", exceptions
            )
