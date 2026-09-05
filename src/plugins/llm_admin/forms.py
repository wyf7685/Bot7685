from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Literal, cast

from nonebot.params import Depends
from pydantic import AnyHttpUrl, TypeAdapter, ValidationError

from src.service.interaction import (
    MISSING,
    ask_bool,
    ask_choice,
    ask_float,
    ask_int,
    ask_secret,
    ask_text,
    ask_value,
)
from src.service.llm import (
    AnthropicThinkingConfig,
    EndpointConfig,
    EndpointProtocol,
    ModelCapabilities,
    ModelConfig,
    ReasoningEffort,
    StructuredOutputMode,
)

_HTTP_URL = TypeAdapter(AnyHttpUrl)
_REASONING_ORDER: tuple[ReasoningEffort, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
_REASONING_BY_PROTOCOL: dict[EndpointProtocol, tuple[ReasoningEffort, ...]] = {
    EndpointProtocol.OPENAI_COMPLETIONS: _REASONING_ORDER,
    EndpointProtocol.OPENAI_RESPONSES: _REASONING_ORDER,
    EndpointProtocol.ANTHROPIC_MESSAGES: (
        "none",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ),
}
_STRUCTURED_ORDER: tuple[StructuredOutputMode, ...] = (
    "json_schema",
    "json_object",
    None,
)
_STRUCTURED_BY_PROTOCOL: dict[EndpointProtocol, tuple[StructuredOutputMode, ...]] = {
    EndpointProtocol.OPENAI_COMPLETIONS: _STRUCTURED_ORDER,
    EndpointProtocol.OPENAI_RESPONSES: _STRUCTURED_ORDER,
    EndpointProtocol.ANTHROPIC_MESSAGES: ("json_schema", None),
}
_PROTOCOL_CHOICES: tuple[tuple[str, EndpointProtocol], ...] = (
    (
        "OpenAI Chat Completions (openai-completions)",
        EndpointProtocol.OPENAI_COMPLETIONS,
    ),
    ("OpenAI Responses (openai-responses)", EndpointProtocol.OPENAI_RESPONSES),
    ("Anthropic Messages (anthropic-messages)", EndpointProtocol.ANTHROPIC_MESSAGES),
)
_DEFAULT_BASE_URLS: dict[EndpointProtocol, AnyHttpUrl] = {
    EndpointProtocol.OPENAI_COMPLETIONS: _HTTP_URL.validate_python(
        "https://api.openai.com/v1"
    ),
    EndpointProtocol.OPENAI_RESPONSES: _HTTP_URL.validate_python(
        "https://api.openai.com/v1"
    ),
    EndpointProtocol.ANTHROPIC_MESSAGES: _HTTP_URL.validate_python(
        "https://api.anthropic.com"
    ),
}
type _ThinkingType = Literal["disabled", "adaptive", "enabled"] | None


class EndpointOptionError(ValueError):
    pass


class ModelOptionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class EndpointFormOptions:
    protocol: str | None = None
    base_url: str | None = None
    timeout_seconds: float | None = None
    max_retries: int | None = None


def _endpoint_form_options(
    protocol: str | None = None,
    base_url: str | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
) -> EndpointFormOptions:
    return EndpointFormOptions(
        protocol=protocol,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


type EndpointOptions = Annotated[EndpointFormOptions, Depends(_endpoint_form_options)]


@dataclass(frozen=True, slots=True)
class ModelFormOptions:
    endpoint: str | None = None
    model_id: str | None = None
    max_concurrent: int | None = None
    default_max_output_tokens: str | None = None
    tools: bool | None = None
    vision: bool | None = None
    temperature: bool | None = None
    reasoning_efforts: str | None = None
    structured_output_modes: str | None = None
    parallel_tool_calls: bool | None = None
    anthropic_thinking: str | None = None
    anthropic_thinking_budget: int | None = None
    selectable: bool | None = None


def _model_form_options(
    endpoint: str | None = None,
    model_id: str | None = None,
    max_concurrent: int | None = None,
    default_max_output_tokens: str | None = None,
    tools: bool | None = None,
    vision: bool | None = None,
    temperature: bool | None = None,
    reasoning_efforts: str | None = None,
    structured_output_modes: str | None = None,
    parallel_tool_calls: bool | None = None,
    anthropic_thinking: str | None = None,
    anthropic_thinking_budget: int | None = None,
    selectable: bool | None = None,
) -> ModelFormOptions:
    return ModelFormOptions(
        endpoint=endpoint,
        model_id=model_id,
        max_concurrent=max_concurrent,
        default_max_output_tokens=default_max_output_tokens,
        tools=tools,
        vision=vision,
        temperature=temperature,
        reasoning_efforts=reasoning_efforts,
        structured_output_modes=structured_output_modes,
        parallel_tool_calls=parallel_tool_calls,
        anthropic_thinking=anthropic_thinking,
        anthropic_thinking_budget=anthropic_thinking_budget,
        selectable=selectable,
    )


type ModelOptions = Annotated[ModelFormOptions, Depends(_model_form_options)]


def _parse_alias(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError
    return value


def _parse_protocol(value: str) -> EndpointProtocol:
    try:
        return EndpointProtocol(value.strip().casefold())
    except ValueError as error:
        raise ValueError from error


def _parse_url(value: str) -> AnyHttpUrl:
    try:
        return _HTTP_URL.validate_python(value)
    except Exception as error:
        raise ValueError from error


def _parse_optional_positive_int(value: str) -> int | None:
    if value.strip().casefold() in {"", "-", "空", "none", "null"}:
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError
    return parsed


def _parse_reasoning_efforts(
    value: str,
    allowed: tuple[ReasoningEffort, ...],
) -> tuple[ReasoningEffort, ...]:
    if not value or value in {"-", "空"}:
        return ()
    items = tuple(item.strip().casefold() for item in value.split(","))
    if len(items) != len(set(items)) or any(item not in allowed for item in items):
        raise ValueError
    typed = cast("tuple[ReasoningEffort, ...]", items)
    positions = tuple(_REASONING_ORDER.index(item) for item in typed)
    if positions != tuple(sorted(positions)):
        raise ValueError
    return typed


def _parse_structured_modes(
    value: str,
    allowed: tuple[StructuredOutputMode, ...],
) -> tuple[StructuredOutputMode, ...]:
    if not value or value in {"-", "空"}:
        return ()
    raw = tuple(item.strip().casefold() for item in value.split(","))
    mapping: dict[str, StructuredOutputMode] = {
        "json_schema": "json_schema",
        "json_object": "json_object",
        "none": None,
        "null": None,
    }
    try:
        modes = tuple(mapping[item] for item in raw)
    except KeyError as error:
        raise ValueError from error
    if len(modes) != len(set(modes)) or any(mode not in allowed for mode in modes):
        raise ValueError
    positions = tuple(_STRUCTURED_ORDER.index(mode) for mode in modes)
    if positions != tuple(sorted(positions)):
        raise ValueError
    return modes


def _parse_thinking_type(value: str) -> _ThinkingType:
    normalized = value.strip().casefold()
    if normalized in {"", "-", "空", "none", "null"}:
        return None
    if normalized not in {"disabled", "adaptive", "enabled"}:
        raise ValueError
    return cast("_ThinkingType", normalized)


async def ask_alias(prompt: str, existing: Mapping[str, object]) -> str:
    def parse(value: str) -> str:
        alias = _parse_alias(value)
        if alias in existing:
            raise ValueError
        return alias

    return await ask_value(
        prompt,
        parse,
        error_message="别名不能为空且不能与现有别名重复。",
    )


async def ask_endpoint(
    *,
    alias: str,
    existing: EndpointConfig | None = None,
    options: EndpointFormOptions | None = None,
) -> EndpointConfig:
    options = options or EndpointFormOptions()

    if options.protocol is None:
        protocol = await ask_choice(
            f"请选择 endpoint {alias!r} 的协议",
            _PROTOCOL_CHOICES,
            default=existing.protocol if existing else MISSING,
        )
    else:
        try:
            protocol = _parse_protocol(options.protocol)
        except ValueError as error:
            raise EndpointOptionError("Endpoint 协议无效。") from error

    protocol_changed = existing is not None and existing.protocol is not protocol
    base_default = (
        existing.base_url
        if existing is not None and not protocol_changed
        else _DEFAULT_BASE_URLS[protocol]
    )
    if options.base_url is None:
        if protocol_changed:
            base_hint = f"。协议已变更，必须重新确认；回复“默认”使用 {base_default}"
        elif existing is not None:
            base_hint = f"，回复“默认”保留 {base_default}"
        else:
            base_hint = f" [默认 {base_default}；回复“默认”使用]"
        base_url = await ask_value(
            f"请输入 endpoint {alias!r} 的 Base URL{base_hint}",
            _parse_url,
            default=base_default,
            error_message="请输入有效的 HTTP 或 HTTPS URL。",
        )
    else:
        try:
            base_url = _parse_url(options.base_url)
        except ValueError as error:
            raise EndpointOptionError("Endpoint Base URL 无效。") from error

    api_key = await ask_secret(
        f"请输入 endpoint {alias!r} 的 API Key",
        default=existing.api_key if existing else MISSING,
    )

    timeout_seconds = options.timeout_seconds
    if timeout_seconds is None:
        timeout_seconds = await ask_float(
            "请输入请求超时秒数"
            + (
                f"，回复“默认”保留 {float(existing.timeout_seconds):g}"
                if existing
                else " [默认 60；回复“默认”使用]"
            ),
            minimum_exclusive=0,
            default=float(existing.timeout_seconds) if existing else 60.0,
        )
    elif timeout_seconds <= 0:
        raise EndpointOptionError("请求超时秒数必须大于 0。")

    max_retries = options.max_retries
    if max_retries is None:
        max_retries = await ask_int(
            "请输入最大重试次数"
            + (
                f"，回复“默认”保留 {int(existing.max_retries)}"
                if existing
                else " [默认 1；回复“默认”使用]"
            ),
            minimum=0,
            default=int(existing.max_retries) if existing else 1,
        )
    elif max_retries < 0:
        raise EndpointOptionError("最大重试次数不能小于 0。")

    try:
        return EndpointConfig(
            protocol=protocol,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
        )
    except ValidationError as error:
        raise EndpointOptionError("Endpoint 配置无效，请检查输入。") from error


async def ask_capabilities(
    protocol: EndpointProtocol,
    existing: ModelCapabilities | None = None,
    options: ModelFormOptions | None = None,
) -> ModelCapabilities:
    options = options or ModelFormOptions()

    tools = options.tools
    if tools is None:
        tools = await ask_bool(
            "模型是否支持工具调用",
            default=existing.tools if existing else False,
        )

    vision = options.vision
    if vision is None:
        vision = await ask_bool(
            "模型是否支持图片输入",
            default=existing.vision if existing else False,
        )

    temperature = options.temperature
    if temperature is None:
        temperature = await ask_bool(
            "模型是否支持 temperature 参数",
            default=existing.temperature if existing else True,
        )

    allowed_reasoning = _REASONING_BY_PROTOCOL[protocol]
    reasoning_default = existing.reasoning_efforts if existing else ()
    reasoning_default_valid = all(
        effort in allowed_reasoning for effort in reasoning_default
    )
    if options.reasoning_efforts is None:
        allowed_display = ",".join(allowed_reasoning)
        if existing and reasoning_default_valid:
            reasoning_hint = (
                f"；回复“默认”保留 {",".join(reasoning_default) or "<空>"}，"
                "回复“空”清空"
            )
        elif existing:
            reasoning_hint = "；现有值与所选协议不兼容，必须重新输入"
        else:
            reasoning_hint = "；回复“默认”表示不支持"
        reasoning = await ask_value(
            f"请输入支持的 reasoning effort，按 {allowed_display} 顺序用逗号分隔"
            + reasoning_hint,
            lambda value: _parse_reasoning_efforts(value, allowed_reasoning),
            default=reasoning_default if reasoning_default_valid else MISSING,
            error_message="reasoning effort 与所选协议不兼容或顺序错误。",
        )
    else:
        try:
            reasoning = _parse_reasoning_efforts(
                options.reasoning_efforts, allowed_reasoning
            )
        except ValueError as error:
            raise ModelOptionError(
                "reasoning effort 与所选协议不兼容或顺序错误。"
            ) from error

    allowed_structured = _STRUCTURED_BY_PROTOCOL[protocol]
    structured_default = existing.structured_output_modes if existing else ()
    structured_default_valid = all(
        mode in allowed_structured for mode in structured_default
    )
    if options.structured_output_modes is None:
        allowed_display = ",".join(
            "none" if mode is None else mode for mode in allowed_structured
        )
        structured_display = ",".join(
            "none" if mode is None else mode for mode in structured_default
        )
        if existing and structured_default_valid:
            structured_hint = (
                f"；回复“默认”保留 {structured_display or "<空>"}，回复“空”清空"
            )
        elif existing:
            structured_hint = "；现有值与所选协议不兼容，必须重新输入"
        else:
            structured_hint = "；回复“默认”表示不支持"
        structured = await ask_value(
            f"请输入 structured output modes，按 {allowed_display} 顺序用逗号分隔"
            + structured_hint,
            lambda value: _parse_structured_modes(value, allowed_structured),
            default=structured_default if structured_default_valid else MISSING,
            error_message="structured output modes 与所选协议不兼容或顺序错误。",
        )
    else:
        try:
            structured = _parse_structured_modes(
                options.structured_output_modes, allowed_structured
            )
        except ValueError as error:
            raise ModelOptionError(
                "structured output modes 与所选协议不兼容或顺序错误。"
            ) from error

    if tools:
        parallel = options.parallel_tool_calls
        if parallel is None:
            parallel = await ask_bool(
                "模型是否支持并行工具调用",
                default=(
                    existing.parallel_tool_calls
                    if existing and existing.tools
                    else False
                ),
            )
    else:
        if options.parallel_tool_calls:
            raise ModelOptionError("启用并行工具调用前必须启用工具调用。")
        parallel = False

    try:
        return ModelCapabilities(
            tools=tools,
            vision=vision,
            temperature=temperature,
            reasoning_efforts=reasoning,
            structured_output_modes=structured,
            parallel_tool_calls=parallel,
        )
    except ValidationError as error:
        raise ModelOptionError("模型能力配置无效，请检查输入。") from error


async def _ask_anthropic_thinking(
    protocol: EndpointProtocol,
    existing: ModelConfig | None,
    options: ModelFormOptions,
) -> AnthropicThinkingConfig | None:
    existing_thinking = existing.anthropic_thinking if existing else None
    if protocol is not EndpointProtocol.ANTHROPIC_MESSAGES:
        if options.anthropic_thinking_budget is not None:
            raise ModelOptionError(
                "Anthropic thinking 仅适用于 anthropic-messages endpoint。"
            )
        if options.anthropic_thinking is not None:
            try:
                requested = _parse_thinking_type(options.anthropic_thinking)
            except ValueError as error:
                raise ModelOptionError(
                    "非 Anthropic 模型请使用 --anthropic-thinking none 清空设置。"
                ) from error
            if requested is not None:
                raise ModelOptionError(
                    "非 Anthropic 模型请使用 --anthropic-thinking none 清空设置。"
                )
            return None
        if existing_thinking is not None and not await ask_bool(
            "所选 endpoint 不支持 Anthropic thinking，确认清空该设置",
            default=False,
        ):
            raise ModelOptionError("未清空 Anthropic thinking，模型配置未更新。")
        return None

    thinking_type: _ThinkingType
    if options.anthropic_thinking is None:
        thinking_type = await ask_choice(
            "请选择 Anthropic thinking 设置",
            (
                ("不发送 thinking 配置 (none)", None),
                ("禁用 (disabled)", "disabled"),
                ("自适应 (adaptive)", "adaptive"),
                ("固定预算 (enabled)", "enabled"),
            ),
            default=existing_thinking.type if existing_thinking else None,
        )
    else:
        try:
            thinking_type = _parse_thinking_type(options.anthropic_thinking)
        except ValueError as error:
            raise ModelOptionError(
                "Anthropic thinking 必须为 none、disabled、adaptive 或 enabled。"
            ) from error

    budget = options.anthropic_thinking_budget
    if thinking_type == "enabled":
        if budget is None:
            existing_budget = (
                existing_thinking.budget_tokens
                if existing_thinking is not None and existing_thinking.type == "enabled"
                else MISSING
            )
            budget = await ask_int(
                "请输入 Anthropic thinking token 预算（必须小于默认最大输出 token）",
                minimum=1024,
                default=existing_budget if existing_budget is not None else MISSING,
            )
        elif budget < 1024:
            raise ModelOptionError("Anthropic thinking token 预算必须不小于 1024。")
    elif budget is not None:
        raise ModelOptionError("仅 enabled Anthropic thinking 可设置 token 预算。")

    if thinking_type is None:
        return None
    try:
        return AnthropicThinkingConfig(type=thinking_type, budget_tokens=budget)
    except ValidationError as error:
        raise ModelOptionError("Anthropic thinking 配置无效。") from error


async def ask_model(
    *,
    alias: str,
    endpoints: Mapping[str, EndpointConfig],
    existing: ModelConfig | None = None,
    force_selectable: bool = False,
    options: ModelFormOptions | None = None,
) -> ModelConfig:
    options = options or ModelFormOptions()

    endpoint_alias = options.endpoint
    if endpoint_alias is None:
        endpoint_alias = await ask_choice(
            f"请选择模型 {alias!r} 使用的 endpoint",
            [(endpoint_alias, endpoint_alias) for endpoint_alias in sorted(endpoints)],
            default=existing.endpoint if existing else MISSING,
        )
    else:
        endpoint_alias = endpoint_alias.strip()
        if endpoint_alias not in endpoints:
            raise ModelOptionError(f"未找到 endpoint：{endpoint_alias or "<空>"}")
    protocol = endpoints[endpoint_alias].protocol

    model_id = options.model_id
    if model_id is None:
        model_id = await ask_text(
            "请输入 Provider 模型 ID"
            + (f"，回复“默认”保留 {existing.model}" if existing else ""),
            default=existing.model if existing else MISSING,
        )
    else:
        model_id = model_id.strip()
        if not model_id:
            raise ModelOptionError("Provider 模型 ID 不能为空。")

    max_concurrent = options.max_concurrent
    if max_concurrent is None:
        max_concurrent = await ask_int(
            "请输入模型最大并发数"
            + (
                f"，回复“默认”保留 {int(existing.max_concurrent)}"
                if existing
                else " [默认 1；回复“默认”使用]"
            ),
            minimum=1,
            default=int(existing.max_concurrent) if existing else 1,
        )
    elif max_concurrent < 1:
        raise ModelOptionError("模型最大并发数必须不小于 1。")

    if options.default_max_output_tokens is not None:
        try:
            default_max_output_tokens = _parse_optional_positive_int(
                options.default_max_output_tokens
            )
        except (TypeError, ValueError) as error:
            raise ModelOptionError("默认最大输出 token 必须为正整数或“空”。") from error
    elif protocol is EndpointProtocol.ANTHROPIC_MESSAGES:
        existing_default = (
            int(existing.default_max_output_tokens)
            if existing and existing.default_max_output_tokens is not None
            else MISSING
        )
        default_max_output_tokens = await ask_int(
            "请输入默认最大输出 token（Anthropic Messages 必填）",
            minimum=1,
            default=existing_default,
        )
    else:
        existing_default = (
            int(existing.default_max_output_tokens)
            if existing and existing.default_max_output_tokens is not None
            else None
        )
        default_max_output_tokens = await ask_value(
            "请输入默认最大输出 token；回复“空”表示不设置"
            + (
                f"，回复“默认”保留 {existing_default or "<空>"}"
                if existing
                else "；回复“默认”表示不设置"
            ),
            _parse_optional_positive_int,
            default=existing_default,
            error_message="请输入正整数或“空”。",
        )
    if (
        protocol is EndpointProtocol.ANTHROPIC_MESSAGES
        and default_max_output_tokens is None
    ):
        raise ModelOptionError("Anthropic Messages 必须配置默认最大输出 token。")

    capabilities = await ask_capabilities(
        protocol,
        existing.capabilities if existing else None,
        options,
    )
    anthropic_thinking = await _ask_anthropic_thinking(protocol, existing, options)

    if force_selectable:
        if options.selectable is False:
            raise ModelOptionError("当前活动模型必须允许作为全局活动模型。")
        selectable = True
    elif options.selectable is None:
        selectable = await ask_bool(
            "模型是否允许作为全局活动模型",
            default=existing.selectable if existing else True,
        )
    else:
        selectable = options.selectable

    try:
        model = ModelConfig(
            endpoint=endpoint_alias,
            model=model_id,
            max_concurrent=max_concurrent,
            default_max_output_tokens=default_max_output_tokens,
            capabilities=capabilities,
            anthropic_thinking=anthropic_thinking,
            selectable=selectable,
        )
        model.validate_for_protocol(protocol)
    except (ValidationError, ValueError) as error:
        raise ModelOptionError("模型配置与所选 endpoint 协议不兼容。") from error
    return model


__all__ = [
    "EndpointFormOptions",
    "EndpointOptionError",
    "EndpointOptions",
    "ModelFormOptions",
    "ModelOptionError",
    "ModelOptions",
    "ask_alias",
    "ask_capabilities",
    "ask_endpoint",
    "ask_model",
]
