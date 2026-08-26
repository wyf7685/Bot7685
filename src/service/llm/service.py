"""Public one-shot LLM service backed by the process-local SDK runtime."""

import asyncio
from collections.abc import Sequence
from threading import Lock
from time import perf_counter
from typing import Any, cast

from nonebot import get_driver

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
from ._selection import ActiveModelStore, active_model_store
from .config import LLMConfig, service_config
from .conversation import run_agent as run_agent_conversation
from .exceptions import (
    LLMCapabilityError,
    LLMConfigurationError,
    LLMErrorCategory,
    LLMRunError,
)
from .models import (
    AgentLimits,
    AgentRunResult,
    ChatInput,
    ModelInfo,
    RunResult,
    StructuredOutputMode,
    StructuredRunResult,
)
from .models import (
    StructuredOutputFallbackReason as FallbackReason,
)
from .runtime import LLMRuntime, ModelHandle
from .tools import BoundTool
from .usage import TokenUsage

_DEFAULT_AGENT_LIMITS = AgentLimits()


class LLMService:
    """Execute isolated model calls and own the global active-model policy."""

    def __init__(
        self,
        runtime: LLMRuntime,
        config: LLMConfig,
        model_store: ActiveModelStore = active_model_store,
    ) -> None:
        self._runtime = runtime
        self._config = config
        self._model_store = model_store

    def list_models(self) -> tuple[ModelInfo, ...]:
        """Return immutable descriptions for every configured model alias."""
        return tuple(self.get_model(alias) for alias in self._config.models)

    def get_model(self, alias: str) -> ModelInfo:
        """Return one configured model description."""
        handle = self._runtime.resolve(alias.strip())
        capabilities = handle.capabilities
        return ModelInfo(
            alias=handle.alias,
            model_id=handle.model_id,
            tools=capabilities.tools,
            vision=capabilities.vision,
            structured_output_modes=capabilities.structured_output_modes,
            parallel_tool_calls=capabilities.parallel_tool_calls,
            selectable=handle.alias in self._config.selectable_models,
        )

    async def get_active_model(self) -> ModelInfo:
        """Return one stable snapshot of the global active model."""
        state = await self._model_store.snapshot(self._config)
        return self.get_model(state.active_model)

    async def select_model(self, alias: str) -> ModelInfo:
        """Persist and return one globally selectable model."""
        state = await self._model_store.select(alias, self._config)
        return self.get_model(state.active_model)

    async def _resolve_model_alias(self, model: str | None) -> str:
        if model is not None:
            return model
        return (await self.get_active_model()).alias

    async def aclose(self) -> None:
        await self._runtime.aclose()

    async def complete_text(
        self,
        prompt: ChatInput,
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> RunResult[str]:
        model_alias = await self._resolve_model_alias(model)
        async with self._runtime.lease(model_alias) as handle:
            self._enforce_capabilities(handle, prompt)
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
        output_type: object,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> StructuredRunResult[T]:
        model_alias = await self._resolve_model_alias(model)
        async with self._runtime.lease(model_alias) as handle:
            self._enforce_capabilities(handle, prompt)
            if not handle.capabilities.structured_output_modes:
                raise LLMCapabilityError(model_alias=handle.alias)
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
        limits: AgentLimits = _DEFAULT_AGENT_LIMITS,
        correlation_id: str | None = None,
    ) -> AgentRunResult:
        """Run one bounded conversation under a single runtime lease."""

        model_alias = await self._resolve_model_alias(model)
        async with self._runtime.lease(model_alias) as handle:
            self._enforce_capabilities(handle, prompt)
            return await run_agent_conversation(
                OpenAIAgentCompletionBackend(handle),
                prompt,
                tools=tools,
                system_prompt=system_prompt,
                model=handle.alias,
                temperature=temperature,
                limits=limits,
                correlation_id=correlation_id,
            )

    @staticmethod
    def _enforce_capabilities(handle: ModelHandle, prompt: ChatInput) -> None:
        if prompt.has_images and not handle.capabilities.vision:
            raise LLMCapabilityError(model_alias=handle.alias)


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
            _service = LLMService(LLMRuntime(service_config), service_config)
        return _service


@get_driver().on_shutdown
async def _close_llm_service() -> None:
    global _service_shutdown_started
    with _service_lock:
        _service_shutdown_started = True
        service = _service
    if service is not None:
        await service.aclose()
