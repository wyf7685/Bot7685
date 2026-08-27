from collections.abc import Mapping
from typing import cast

from pydantic import AnyHttpUrl, TypeAdapter

from src.service.llm import (
    EndpointConfig,
    ModelCapabilities,
    ModelConfig,
    ReasoningEffort,
    StructuredOutputMode,
)

from .interaction import (
    ask_bool,
    ask_choice,
    ask_float,
    ask_int,
    ask_text,
    ask_value,
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
_STRUCTURED_ORDER: tuple[StructuredOutputMode, ...] = (
    "json_schema",
    "json_object",
    None,
)


def _parse_alias(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError
    return value


def _parse_url(value: str) -> AnyHttpUrl:
    try:
        return _HTTP_URL.validate_python(value)
    except Exception as error:
        raise ValueError from error


def _parse_reasoning_efforts(value: str) -> tuple[ReasoningEffort, ...]:
    if not value or value in {"-", "空"}:
        return ()
    items = tuple(item.strip().casefold() for item in value.split(","))
    if len(items) != len(set(items)) or any(
        item not in _REASONING_ORDER for item in items
    ):
        raise ValueError
    typed = tuple(items)
    positions = tuple(_REASONING_ORDER.index(item) for item in typed)
    if positions != tuple(sorted(positions)):
        raise ValueError
    return cast("tuple[ReasoningEffort, ...]", typed)


def _parse_structured_modes(value: str) -> tuple[StructuredOutputMode, ...]:
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
    if len(modes) != len(set(modes)):
        raise ValueError
    positions = tuple(_STRUCTURED_ORDER.index(mode) for mode in modes)
    if positions != tuple(sorted(positions)):
        raise ValueError
    return modes


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
) -> EndpointConfig:
    base_url = await ask_value(
        f"请输入 endpoint {alias!r} 的 Base URL"
        + (f"，留空保留 {existing.base_url}" if existing else ""),
        _parse_url,
        default=existing.base_url if existing else None,
        allow_empty_default=existing is not None,
        error_message="请输入有效的 HTTP 或 HTTPS URL。",
    )
    api_key = await ask_text(
        f"请输入 endpoint {alias!r} 的 API Key"
        + ("，留空保留当前值" if existing else ""),
        default=existing.api_key.get_secret_value() if existing else None,
        allow_empty_default=existing is not None,
    )
    timeout_prompt = (
        f"，留空保留 {float(existing.timeout_seconds):g}" if existing else " [默认 60]"
    )
    timeout_seconds = await ask_float(
        "请输入请求超时秒数" + timeout_prompt,
        minimum_exclusive=0,
        default=float(existing.timeout_seconds) if existing else 60.0,
        allow_empty_default=True,
    )
    max_retries = await ask_int(
        "请输入最大重试次数"
        + (f"，留空保留 {int(existing.max_retries)}" if existing else " [默认 1]"),
        minimum=0,
        default=int(existing.max_retries) if existing else 1,
        allow_empty_default=True,
    )
    return EndpointConfig(
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )


async def ask_capabilities(
    existing: ModelCapabilities | None = None,
) -> ModelCapabilities:
    tools = await ask_bool(
        "模型是否支持工具调用" + ("，留空保留当前值" if existing else ""),
        default=existing.tools if existing else False,
        allow_empty_default=True,
    )
    vision = await ask_bool(
        "模型是否支持图片输入" + ("，留空保留当前值" if existing else ""),
        default=existing.vision if existing else False,
        allow_empty_default=True,
    )
    reasoning_default = existing.reasoning_efforts if existing else ()
    reasoning_hint = (
        f"；留空保留 {",".join(reasoning_default) or "<空>"}，回复“空”清空"
        if existing
        else "；留空表示不支持"
    )
    reasoning = await ask_value(
        "请输入支持的 reasoning effort，按 "
        "none,minimal,low,medium,high,xhigh,max 顺序用逗号分隔" + reasoning_hint,
        _parse_reasoning_efforts,
        default=reasoning_default,
        allow_empty_default=True,
        error_message="reasoning effort 无效或顺序错误。",
    )
    structured_default = existing.structured_output_modes if existing else ()
    structured_display = ",".join(
        "none" if mode is None else mode for mode in structured_default
    )
    structured_hint = (
        f"；留空保留 {structured_display or "<空>"}，回复“空”清空"
        if existing
        else "；留空表示不支持"
    )
    structured = await ask_value(
        "请输入 structured output modes，按 "
        "json_schema,json_object,none 顺序用逗号分隔" + structured_hint,
        _parse_structured_modes,
        default=structured_default,
        allow_empty_default=True,
        error_message="structured output modes 无效或顺序错误。",
    )
    parallel = False
    if tools:
        parallel = await ask_bool(
            "模型是否支持并行工具调用" + ("，留空保留当前值" if existing else ""),
            default=existing.parallel_tool_calls if existing else False,
            allow_empty_default=True,
        )
    return ModelCapabilities(
        tools=tools,
        vision=vision,
        reasoning_efforts=reasoning,
        structured_output_modes=structured,
        parallel_tool_calls=parallel,
    )


async def ask_model(
    *,
    alias: str,
    endpoints: Mapping[str, EndpointConfig],
    existing: ModelConfig | None = None,
    force_selectable: bool = False,
) -> ModelConfig:
    endpoint_alias = await ask_choice(
        f"请选择模型 {alias!r} 使用的 endpoint",
        [(endpoint_alias, endpoint_alias) for endpoint_alias in sorted(endpoints)],
        default=existing.endpoint if existing else None,
        allow_empty_default=existing is not None,
    )
    model_id = await ask_text(
        "请输入 Provider 模型 ID"
        + (f"，留空保留 {existing.model}" if existing else ""),
        default=existing.model if existing else None,
        allow_empty_default=existing is not None,
    )
    max_concurrent = await ask_int(
        "请输入模型最大并发数"
        + (f"，留空保留 {int(existing.max_concurrent)}" if existing else " [默认 1]"),
        minimum=1,
        default=int(existing.max_concurrent) if existing else 1,
        allow_empty_default=True,
    )
    capabilities = await ask_capabilities(existing.capabilities if existing else None)
    selectable = True
    if not force_selectable:
        selectable = await ask_bool(
            "模型是否允许作为全局活动模型" + ("，留空保留当前值" if existing else ""),
            default=existing.selectable if existing else True,
            allow_empty_default=True,
        )
    return ModelConfig(
        endpoint=endpoint_alias,
        model=model_id,
        max_concurrent=max_concurrent,
        capabilities=capabilities,
        selectable=selectable,
    )


__all__ = ["ask_alias", "ask_capabilities", "ask_endpoint", "ask_model"]
