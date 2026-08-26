from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

from nonebot_plugin_alconna import CustomNode, UniMessage

from src.service.llm import LLMCapabilityError, ModelCapability

from .config import RenderingConfig
from .contracts import (
    ModelStageUsage,
    RenderFailure,
    RenderFailureCategory,
    RenderModel,
    RunStatistics,
    SourceEntry,
    ToolDisplayEntry,
)

if TYPE_CHECKING:
    from src.service.llm import LLMServiceError, TokenUsage

_CITATION_RE = re.compile(r"\[(s[1-9][0-9]*)\]")
_REDIRECT_PATH_PARTS = frozenset({"ck", "l", "link", "redirect", "redir", "url"})
_REDIRECT_HOSTS = frozenset(
    {
        "api.search.brave.com",
        "links.duckduckgo.com",
        "r.search.yahoo.com",
    }
)

_RENDER_FAILURE_MESSAGES = {
    RenderFailureCategory.CONFIGURATION: "ZSSM 配置不可用，请联系管理员。",
    RenderFailureCategory.PERMISSION: "当前会话没有执行此操作的权限。",
    RenderFailureCategory.EMPTY_INPUT: "请在 zssm 后输入内容，或引用一条消息。",
    RenderFailureCategory.UNSUPPORTED_INPUT: "消息中包含暂不支持的内容。",
    RenderFailureCategory.FORWARD: "转发消息内容获取失败，请稍后重试。",
    RenderFailureCategory.IMAGE: "图片处理失败，请换一张图片或稍后重试。",
    RenderFailureCategory.LIMITS: "本次处理达到限制，请缩短内容后重试。",
    RenderFailureCategory.PROVIDER: "模型服务暂时不可用，请稍后重试。",
    RenderFailureCategory.TOOL: "工具调用失败，请稍后重试。",
    RenderFailureCategory.RENDER: "响应发送失败，请稍后重试。",
}

_CAPABILITY_FAILURE_MESSAGES = {
    ModelCapability.TOOLS: "当前模型不支持工具调用。",
    ModelCapability.VISION: "当前模型不支持图片输入。",
    ModelCapability.STRUCTURED_OUTPUT: "当前模型不支持结构化输出。",
    ModelCapability.PARALLEL_TOOL_CALLS: "当前模型不支持并行工具调用。",
}

_LLM_FAILURE_MESSAGES = {
    "configuration": "模型配置不可用，请联系管理员。",
    "capability": "当前模型不支持这类输入。",
    "authentication": "模型服务认证失败，请联系管理员。",
    "rate_limited": "模型服务繁忙，请稍后重试。",
    "timeout": "模型处理超时，请稍后重试。",
    "provider": "模型服务暂时不可用，请稍后重试。",
    "invalid_response": "模型返回了无效结果，请重试。",
    "structured_output": "模型返回了无效结果，请重试。",
    "tool": "工具调用失败，请稍后重试。",
    "limits": "本次处理达到限制，请缩短内容后重试。",
}


class ReferenceSendError(Exception):
    """A safely categorized failure to send the generated Reference."""

    failure: RenderFailure

    def __init__(self) -> None:
        self.failure = RenderFailure(
            RenderFailureCategory.RENDER,
            _RENDER_FAILURE_MESSAGES[RenderFailureCategory.RENDER],
        )
        super().__init__(self.failure.message)


def _split_text(text: str, max_chars: int) -> Iterator[str]:
    while len(text) > max_chars:
        split_at = text.rfind("\n", 1, max_chars)
        split_at = split_at + 1 if split_at >= 1 else max_chars
        chunk = text[:split_at]
        if chunk:
            yield chunk
        text = text[split_at:]
    if text:
        yield text


def _display_text(value: str, max_chars: int) -> str:
    visible = "".join(
        " " if char.isspace() else char
        for char in unicodedata.normalize("NFKC", value)
        if char.isspace() or not unicodedata.category(char).startswith("C")
    )
    compact = " ".join(visible.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 1]}…"


def _safe_display_url(value: str) -> str | None:
    parsed = urlsplit(value)
    host = parsed.hostname
    if host is None:
        return None
    try:
        host = host.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None

    path_parts = {part.lower() for part in parsed.path.split("/") if part}
    if host in _REDIRECT_HOSTS or path_parts & _REDIRECT_PATH_PARTS:
        return None

    if ":" in host:
        host = f"[{host}]"
    port = parsed.port
    if port is not None and not (
        (parsed.scheme.lower() == "http" and port == 80)
        or (parsed.scheme.lower() == "https" and port == 443)
    ):
        host = f"{host}:{port}"

    path = parsed.path or "/"
    display = urlunsplit((parsed.scheme.lower(), host, path, "", ""))
    return _display_text(display, 320) or None


def _render_source(source: SourceEntry) -> str:
    title = _display_text(source.title, 180) or "未命名来源"
    metadata = [
        item
        for value, limit in ((source.source, 80), (source.published, 40))
        if value is not None and (item := _display_text(value, limit))
    ]
    heading = f"[{source.citation_id}] {title}"
    if metadata:
        heading += f"（{" · ".join(metadata)}）"
    if url := _safe_display_url(source.url):
        return f"{heading}\n{url}"
    return heading


def _source_content(model: RenderModel, config: RenderingConfig) -> str | None:
    assert model.answer is not None
    if not config.include_sources:
        return None

    referenced = set(_CITATION_RE.findall(model.answer))
    sources = tuple(
        source for source in model.sources if source.citation_id in referenced
    )
    if not sources:
        return None
    return "参考来源：\n" + "\n".join(_render_source(source) for source in sources)


def _format_seconds(value: float) -> str:
    rendered = f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{rendered or "0"}s"


def _usage_text(usage: TokenUsage | None) -> str:
    if usage is None:
        return "tokens 不可用"
    return (
        f"输入 {usage.prompt_tokens}；输出 {usage.completion_tokens}；"
        f"总计 {usage.total_tokens}"
    )


def _combined_usage_text(stages: Sequence[ModelStageUsage]) -> str:
    if any(stage.usage is None for stage in stages):
        return "tokens 不可用"
    prompt_tokens = sum(
        stage.usage.prompt_tokens for stage in stages if stage.usage is not None
    )
    completion_tokens = sum(
        stage.usage.completion_tokens for stage in stages if stage.usage is not None
    )
    total_tokens = sum(
        stage.usage.total_tokens for stage in stages if stage.usage is not None
    )
    return f"输入 {prompt_tokens}；输出 {completion_tokens}；总计 {total_tokens}"


def _stage_line(label: str, stage: ModelStageUsage) -> str:
    alias = _display_text(stage.model_alias, 80) or "未知模型"
    elapsed = _format_seconds(stage.elapsed)
    return (
        f"{label}（{alias}）: 调用 {stage.calls}；耗时 {elapsed}；"
        f"{_usage_text(stage.usage)}"
    )


def _statistics_content(stats: RunStatistics) -> str:
    stages = (
        (stats.primary_usage,)
        if stats.vision_usage is None
        else (stats.primary_usage, stats.vision_usage)
    )
    failed_images = stats.images.acquisition_failed + stats.images.vision_failed
    total_calls = sum(stage.calls for stage in stages)
    combined_usage = _combined_usage_text(stages)
    lines = [
        "处理统计",
        f"总耗时: {_format_seconds(stats.total_elapsed)}",
        f"模型总计: 调用 {total_calls}；{combined_usage}",
        _stage_line("主模型", stats.primary_usage),
    ]
    if stats.vision_usage is None:
        lines.append("视觉模型: 未使用；调用 0；输入 0；输出 0；总计 0")
    else:
        lines.append(_stage_line("视觉模型", stats.vision_usage))
    partial_success = "是" if stats.images.partial_success else "否"
    lines.extend(
        (
            f"工具: 调用 {stats.tool_calls}；失败 {stats.tool_failures}；"
            f"耗时 {_format_seconds(stats.tool_elapsed)}",
            f"图片: 请求 {stats.images.requested}；准备 {stats.images.prepared}；"
            f"失败 {failed_images}；部分成功 {partial_success}",
        )
    )
    return "\n".join(lines)


def _trace_content(trace: Sequence[ToolDisplayEntry]) -> str:
    lines = ["工具轨迹"]
    for index, entry in enumerate(trace, 1):
        name = _display_text(entry.name, 80) or "工具"
        summary = _display_text(entry.summary, 160) or "无摘要"
        lines.append(
            f"{index}. {name} | {entry.status.value} | "
            f"{_format_seconds(entry.elapsed)} | {summary}"
        )
    return "\n".join(lines)


def _text_nodes(
    text: str,
    *,
    bot_uid: str,
    node_name: str,
    max_chars: int,
) -> Iterator[CustomNode]:
    for chunk in _split_text(text, max_chars):
        yield CustomNode(uid=bot_uid, name=node_name, content=chunk)


def build_reference_nodes(
    model: RenderModel,
    *,
    bot_uid: str,
    config: RenderingConfig,
) -> tuple[CustomNode, ...]:
    """Build the stable, adapter-neutral logical Reference node sequence."""

    if model.failure is not None:
        raise ValueError(
            "failure render models must be rendered as an ordinary message"
        )

    assert model.answer is not None
    nodes: list[CustomNode] = []
    nodes.extend(
        _text_nodes(
            model.answer,
            bot_uid=bot_uid,
            node_name=config.node_name,
            max_chars=config.max_node_chars,
        )
    )
    if source_content := _source_content(model, config):
        nodes.extend(
            _text_nodes(
                source_content,
                bot_uid=bot_uid,
                node_name=config.node_name,
                max_chars=config.max_node_chars,
            )
        )
    nodes.extend(
        _text_nodes(
            "原始消息:",
            bot_uid=bot_uid,
            node_name=config.node_name,
            max_chars=config.max_node_chars,
        )
    )
    nodes.append(
        CustomNode(uid=bot_uid, name=config.node_name, content=model.current.copy())
    )
    if model.quoted is not None:
        nodes.append(
            CustomNode(uid=bot_uid, name=config.node_name, content=model.quoted.copy())
        )
    if config.include_tool_trace and model.trace:
        nodes.extend(
            _text_nodes(
                _trace_content(model.trace),
                bot_uid=bot_uid,
                node_name=config.node_name,
                max_chars=config.max_node_chars,
            )
        )
    assert model.stats is not None
    nodes.extend(
        _text_nodes(
            _statistics_content(model.stats),
            bot_uid=bot_uid,
            node_name=config.node_name,
            max_chars=config.max_node_chars,
        )
    )
    return tuple(nodes)


def render_error(error: RenderFailure | LLMServiceError) -> UniMessage:
    """Map safe error categories to a short ordinary UniMessage."""

    if isinstance(error, RenderFailure):
        message = _RENDER_FAILURE_MESSAGES[error.category]
    elif isinstance(error, LLMCapabilityError):
        message = _CAPABILITY_FAILURE_MESSAGES[error.capability]
    else:
        category = getattr(error, "category", None)
        category_value = getattr(category, "value", None)
        if not isinstance(category_value, str):
            raise TypeError(
                f"unsupported render error type: {type(error).__name__}"
            ) from None
        try:
            message = _LLM_FAILURE_MESSAGES[category_value]
        except KeyError:
            raise TypeError(
                f"unsupported render error type: {type(error).__name__}"
            ) from None
    return UniMessage.text(message)


async def send_reference(nodes: Sequence[CustomNode]) -> None:
    """Send one Reference without inspecting or calling adapter-native APIs."""

    if not nodes:
        raise ValueError("reference requires at least one node")
    try:
        await UniMessage.reference(*nodes).send()
    except asyncio.CancelledError:
        raise
    except Exception:
        raise ReferenceSendError from None


__all__ = [
    "ReferenceSendError",
    "build_reference_nodes",
    "render_error",
    "send_reference",
]
