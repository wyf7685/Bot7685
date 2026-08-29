"""Public one-shot LLM service backed by the process-local SDK runtime."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from time import perf_counter
from types import MappingProxyType
from typing import Any, cast

from nonebot import get_driver, logger
from pydantic import ValidationError

from ._openai_adapter import (
    InvalidSDKResponseError,
    OpenAIAgentCompletionBackend,
    StructuredOutputValidationError,
    build_messages,
    create_completion,
    extract_text,
    is_response_format_unsupported,
    make_envelope_schema,
    make_output_adapter,
    make_response_format,
    normalize_rejected_usage,
    normalize_usage,
    parse_structured_output,
    provider_error_category,
)
from .config import LLMConfig
from .conversation import run_agent as run_agent_conversation
from .exceptions import (
    LLMCapabilityError,
    LLMConfigurationConflictError,
    LLMConfigurationError,
    LLMErrorCategory,
    LLMModelSelectionError,
    LLMRunError,
)
from .models import (
    AgentLimits,
    AgentRunResult,
    ChatInput,
    ModelCapability,
    ModelInfo,
    ReasoningEffort,
    RunResult,
    StructuredOutputMode,
    StructuredRunResult,
)
from .models import StructuredOutputFallbackReason as FallbackReason
from .repository import LLMConfigRepository
from .runtime import LLMRuntime, _ModelHandle
from .tools import BoundTool
from .usage import TokenUsage

_DEFAULT_AGENT_LIMITS = AgentLimits()


@dataclass(frozen=True, slots=True)
class LLMConfigurationSnapshot:
    revision: int
    config: LLMConfig | None
    load_error: bool


@dataclass(frozen=True, slots=True)
class _ServiceState:
    config: LLMConfig
    runtime: LLMRuntime
    models: Mapping[str, ModelInfo]
    model_list: tuple[ModelInfo, ...]


class LLMService:
    """Execute LLM calls against an atomically replaceable runtime snapshot."""

    def __init__(self) -> None:
        self._repository = LLMConfigRepository()
        self._state_lock = asyncio.Lock()
        self._revision = 0
        self._load_error = False
        self._shutdown = False
        self._retired_runtimes: set[asyncio.Task[None]] = set()
        self._state: _ServiceState | None = None

        try:
            config = self._repository.load()
            if config is not None:
                self._state = self._build_state(config)
        except (OSError, ValidationError, ValueError) as error:
            self._load_error = True
            logger.error(
                f"LLM persisted configuration is unavailable: {type(error).__name__}"
            )

    @staticmethod
    def _build_state(config: LLMConfig) -> _ServiceState:
        models = MappingProxyType(
            {
                alias: ModelInfo(
                    alias=alias,
                    model_id=model.model,
                    capabilities=model.capabilities,
                    selectable=model.selectable,
                )
                for alias, model in config.models.items()
            }
        )
        return _ServiceState(
            config=config,
            runtime=LLMRuntime(config),
            models=models,
            model_list=tuple(models.values()),
        )

    async def configuration_snapshot(self) -> LLMConfigurationSnapshot:
        async with self._state_lock:
            return LLMConfigurationSnapshot(
                revision=self._revision,
                config=self._state.config if self._state is not None else None,
                load_error=self._load_error,
            )

    async def replace_configuration(
        self,
        config: LLMConfig,
        *,
        expected_revision: int,
    ) -> int:
        candidate = self._build_state(config)
        previous: _ServiceState | None
        try:
            async with self._state_lock:
                self._ensure_open()
                if expected_revision != self._revision:
                    raise LLMConfigurationConflictError
                try:
                    self._repository.save(config)
                except OSError as error:
                    raise LLMConfigurationError(cause=error) from error
                previous = self._state
                self._state = candidate
                self._load_error = False
                self._revision += 1
                revision = self._revision
        except BaseException:
            await self._close_runtime(candidate.runtime)
            raise

        if previous is not None:
            self._retire_runtime(previous.runtime)
        return revision

    async def reset_configuration(self, *, expected_revision: int) -> int:
        async with self._state_lock:
            self._ensure_open()
            if expected_revision != self._revision:
                raise LLMConfigurationConflictError
            try:
                self._repository.delete()
            except OSError as error:
                raise LLMConfigurationError(cause=error) from error
            previous = self._state
            self._state = None
            self._load_error = False
            self._revision += 1
            revision = self._revision

        if previous is not None:
            self._retire_runtime(previous.runtime)
        return revision

    def list_models(self) -> tuple[ModelInfo, ...]:
        state = self._state
        return state.model_list if state is not None else ()

    def get_model(self, alias: str) -> ModelInfo:
        state = self._state
        normalized = alias.strip()
        if state is None:
            raise LLMConfigurationError(model_alias=normalized)
        try:
            return state.models[normalized]
        except KeyError as error:
            raise LLMConfigurationError(model_alias=normalized) from error

    async def get_active_model(self) -> ModelInfo:
        async with self._state_lock:
            self._ensure_open()
            state = self._require_state()
            return state.models[state.config.active_model]

    async def select_model(self, alias: str) -> ModelInfo:
        normalized = alias.strip()
        async with self._state_lock:
            self._ensure_open()
            state = self._require_state()
            model = state.models.get(normalized)
            if model is None:
                raise LLMModelSelectionError("未找到该模型。")
            if not model.selectable:
                raise LLMModelSelectionError("该模型不可切换。")

            config = state.config.model_copy(update={"active_model": normalized})
            try:
                self._repository.save(config)
            except OSError as error:
                raise LLMConfigurationError(cause=error) from error
            self._state = _ServiceState(
                config=config,
                runtime=state.runtime,
                models=state.models,
                model_list=state.model_list,
            )
            self._revision += 1
            return model

    @asynccontextmanager
    async def _lease_model(self, model: str | None) -> AsyncIterator[_ModelHandle]:
        stack = AsyncExitStack()
        try:
            async with self._state_lock:
                self._ensure_open()
                state = self._require_state()
                alias = (
                    model.strip() if model is not None else state.config.active_model
                )
                handle = await stack.enter_async_context(state.runtime.lease(alias))
            yield handle
        finally:
            await stack.aclose()

    async def aclose(self) -> None:
        async with self._state_lock:
            if self._shutdown:
                return
            self._shutdown = True
            state = self._state
            self._state = None

        if state is not None:
            await self._close_runtime(state.runtime)
        retired = tuple(self._retired_runtimes)
        if retired:
            await asyncio.gather(*retired, return_exceptions=True)

    def _ensure_open(self) -> None:
        if self._shutdown:
            raise LLMConfigurationError

    def _require_state(self) -> _ServiceState:
        if self._state is None:
            raise LLMConfigurationError
        return self._state

    def _retire_runtime(self, runtime: LLMRuntime) -> None:
        task = asyncio.create_task(self._close_runtime(runtime))
        self._retired_runtimes.add(task)
        task.add_done_callback(self._retired_runtimes.discard)

    @staticmethod
    async def _close_runtime(runtime: LLMRuntime) -> None:
        try:
            await runtime.aclose()
        except Exception as error:
            logger.warning(f"Failed to close an LLM runtime: {type(error).__name__}")

    async def complete_text(
        self,
        prompt: ChatInput,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> RunResult[str]:
        async with self._lease_model(model) as handle:
            self._enforce_capabilities(handle, prompt)
            effective_reasoning_effort = self._resolve_reasoning_effort(
                handle, reasoning_effort
            )
            messages = build_messages(
                prompt,
                system_prompt,
                structured_schema=None,
            )
            started = perf_counter()

            async with handle.semaphore:
                try:
                    completion = await create_completion(
                        handle.client,
                        model_id=handle.model_id,
                        messages=messages,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        reasoning_effort=effective_reasoning_effort,
                    )
                    output = extract_text(completion)
                    usage = normalize_usage(completion)
                except asyncio.CancelledError:
                    raise
                except InvalidSDKResponseError as error:
                    raise LLMRunError(
                        category=LLMErrorCategory.INVALID_RESPONSE,
                        model_alias=handle.alias,
                        cause=error,
                    ) from error
                except Exception as error:
                    category = provider_error_category(error)
                    if category is None:
                        raise
                    raise LLMRunError(
                        category=category,
                        model_alias=handle.alias,
                        cause=error,
                    ) from error

            return RunResult(
                output=output,
                model_alias=handle.alias,
                model_id=handle.model_id,
                usage=usage,
                elapsed=perf_counter() - started,
            )

    async def complete_structured[T](
        self,
        prompt: ChatInput,
        *,
        output_type: type[T],
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> StructuredRunResult[T]:
        async with self._lease_model(model) as handle:
            self._enforce_capabilities(handle, prompt)
            effective_reasoning_effort = self._resolve_reasoning_effort(
                handle, reasoning_effort
            )
            handle.require_capability(ModelCapability.STRUCTURED_OUTPUT)
            try:
                output_adapter = make_output_adapter(output_type)
                envelope_schema = make_envelope_schema(output_adapter)
            except Exception as error:
                raise LLMConfigurationError(
                    model_alias=handle.alias,
                    cause=error,
                ) from error

            messages = build_messages(
                prompt,
                system_prompt,
                structured_schema=envelope_schema,
            )
            attempted_modes: list[StructuredOutputMode] = []
            fallback_reasons: list[FallbackReason] = []
            rejected_usage = TokenUsage()
            mode = handle.effective_structured_mode()
            started = perf_counter()

            async with handle.semaphore:
                while True:
                    attempted_modes.append(mode)
                    response_format = make_response_format(mode, envelope_schema)

                    try:
                        completion = await create_completion(
                            handle.client,
                            model_id=handle.model_id,
                            messages=messages,
                            temperature=temperature,
                            max_output_tokens=max_output_tokens,
                            response_format=response_format,
                            reasoning_effort=effective_reasoning_effort,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        if is_response_format_unsupported(error, mode):
                            try:
                                rejected_usage += normalize_rejected_usage(error)
                            except InvalidSDKResponseError as usage_error:
                                raise LLMRunError(
                                    category=LLMErrorCategory.INVALID_RESPONSE,
                                    model_alias=handle.alias,
                                    cause=usage_error,
                                ) from usage_error
                            next_mode = handle.downgrade_structured_mode(mode)
                            if next_mode == mode:
                                raise LLMRunError(
                                    category=LLMErrorCategory.STRUCTURED_OUTPUT,
                                    model_alias=handle.alias,
                                    cause=error,
                                ) from error
                            fallback_reasons.append(
                                FallbackReason.RESPONSE_FORMAT_UNSUPPORTED
                            )
                            mode = next_mode
                            continue
                        category = provider_error_category(error)
                        if category is None:
                            raise
                        raise LLMRunError(
                            category=category,
                            model_alias=handle.alias,
                            cause=error,
                        ) from error

                    try:
                        text = extract_text(completion)
                        usage = rejected_usage + normalize_usage(completion)
                    except InvalidSDKResponseError as error:
                        raise LLMRunError(
                            category=LLMErrorCategory.INVALID_RESPONSE,
                            model_alias=handle.alias,
                            cause=error,
                        ) from error

                    try:
                        output = parse_structured_output(text, output_adapter)
                    except StructuredOutputValidationError as error:
                        raise LLMRunError(
                            category=LLMErrorCategory.STRUCTURED_OUTPUT,
                            model_alias=handle.alias,
                            cause=error,
                        ) from error
                    break

            return StructuredRunResult(
                output=cast("T", output),
                model_alias=handle.alias,
                model_id=handle.model_id,
                usage=usage,
                elapsed=perf_counter() - started,
                mode_used=mode,
                attempted_modes=tuple(attempted_modes),
                fallback_reasons=tuple(fallback_reasons),
            )

    async def run_agent(
        self,
        prompt: ChatInput,
        *,
        tools: Sequence[BoundTool[Any, Any]] = (),
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        limits: AgentLimits = _DEFAULT_AGENT_LIMITS,
        correlation_id: str | None = None,
    ) -> AgentRunResult:
        """Run one bounded conversation under a single runtime lease."""

        async with self._lease_model(model) as handle:
            effective_reasoning_effort = self._resolve_reasoning_effort(
                handle, reasoning_effort
            )
            return await run_agent_conversation(
                OpenAIAgentCompletionBackend(handle),
                prompt,
                tools=tools,
                system_prompt=system_prompt,
                temperature=temperature,
                limits=limits,
                reasoning_effort=effective_reasoning_effort,
                correlation_id=correlation_id,
            )

    @staticmethod
    def _resolve_reasoning_effort(
        handle: _ModelHandle,
        requested: ReasoningEffort | None,
    ) -> ReasoningEffort | None:
        try:
            return handle.capabilities.resolve_reasoning_effort(requested)
        except ValueError as error:
            raise LLMCapabilityError(
                model_alias=handle.alias,
                capability=ModelCapability.REASONING_EFFORT,
                cause=error,
            ) from error

    @staticmethod
    def _enforce_capabilities(handle: _ModelHandle, prompt: ChatInput) -> None:
        if prompt.has_images:
            handle.require_capability(ModelCapability.VISION)


_service: LLMService | None = None
_service_lock = Lock()
_service_shutdown_started = False


def get_llm_service() -> LLMService:
    """Return the sole process-local LLM service instance."""
    global _service
    with _service_lock:
        if _service_shutdown_started:
            raise LLMConfigurationError
        if _service is None:
            _service = LLMService()
        return _service


@get_driver().on_shutdown
async def _close_llm_service() -> None:
    global _service_shutdown_started
    with _service_lock:
        _service_shutdown_started = True
        service = _service
    if service is not None:
        await service.aclose()
