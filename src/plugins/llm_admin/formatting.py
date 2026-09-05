from src.service.llm import (
    EndpointConfig,
    LLMConfig,
    LLMConfigurationSnapshot,
    ModelCapabilities,
    ModelConfig,
    ModelInfo,
)


def format_capabilities(capabilities: ModelCapabilities) -> str:
    reasoning = ", ".join(capabilities.reasoning_efforts) or "无"
    structured = (
        ", ".join(
            "none" if mode is None else mode
            for mode in capabilities.structured_output_modes
        )
        or "无"
    )
    return (
        f"tools={capabilities.tools}, vision={capabilities.vision}, "
        f"temperature={capabilities.temperature}, "
        f"parallel_tools={capabilities.parallel_tool_calls}, "
        f"reasoning=[{reasoning}], structured=[{structured}]"
    )


def format_endpoint(alias: str, endpoint: EndpointConfig) -> str:
    return (
        f"- {alias}: {endpoint.base_url}\n"
        f"  protocol={endpoint.protocol.value}, "
        f"timeout={float(endpoint.timeout_seconds):g}s, "
        f"retries={int(endpoint.max_retries)}, api_key=已配置"
    )


def format_model(alias: str, model: ModelConfig, *, active: bool) -> str:
    marker = "（当前）" if active else ""
    max_output = model.default_max_output_tokens or "未设置"
    thinking = model.anthropic_thinking
    thinking_display = thinking.type if thinking is not None else "未设置"
    if thinking is not None and thinking.budget_tokens is not None:
        thinking_display += f"({thinking.budget_tokens})"
    return (
        f"- {alias}{marker}: {model.model}\n"
        f"  endpoint={model.endpoint}, max_concurrent={int(model.max_concurrent)}, "
        f"default_max_output_tokens={max_output}, selectable={model.selectable}\n"
        f"  anthropic_thinking={thinking_display}\n"
        f"  {format_capabilities(model.capabilities)}"
    )


def format_configuration(config: LLMConfig) -> str:
    endpoints = "\n".join(
        format_endpoint(alias, endpoint)
        for alias, endpoint in sorted(config.endpoints.items())
    )
    models = "\n".join(
        format_model(alias, model, active=alias == config.active_model)
        for alias, model in sorted(config.models.items())
    )
    return (
        f"活动模型：{config.active_model}\n\n"
        f"Endpoints:\n{endpoints}\n\n"
        f"Models:\n{models}"
    )


def format_status(snapshot: LLMConfigurationSnapshot) -> str:
    if snapshot.config is None:
        if snapshot.load_error:
            return "LLM 配置文件不可用。请在私聊执行 /llm config setup 重新配置。"
        return "LLM 尚未配置。请在私聊执行 /llm config setup。"
    return format_configuration(snapshot.config)


def format_model_list(active_alias: str, models: tuple[ModelInfo, ...]) -> str:
    selectable = sorted(
        (model for model in models if model.selectable),
        key=lambda model: (model.alias != active_alias, model.alias),
    )
    unavailable = sorted(
        (model for model in models if not model.selectable),
        key=lambda model: model.alias,
    )
    lines = ["可切换模型："]
    lines.extend(
        f"- {model.alias}{"（当前）" if model.alias == active_alias else ""}"
        for model in selectable
    )
    if unavailable:
        lines.extend(("", "不可切换模型："))
        lines.extend(f"- {model.alias}" for model in unavailable)
    return "\n".join(lines)


__all__ = [
    "format_configuration",
    "format_endpoint",
    "format_model",
    "format_model_list",
    "format_status",
]
