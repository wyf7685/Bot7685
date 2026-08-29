import asyncio
import re
from datetime import UTC, datetime
from functools import partial
from time import perf_counter
from weakref import WeakKeyDictionary

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.orm import BotModel, SceneModel, SessionModel, UserModel
from sqlalchemy import func, select

from src.service.llm import AgentLimits, AgentRunResult, LLMService, ModelCapability

from .config import ZssmConfig
from .contracts.output import RenderModel, SourceEntry
from .contracts.run import (
    ModelStageUsage,
    RunStatistics,
    ToolDisplayEntry,
    ToolDisplayStatus,
    ZssmInvocationFacts,
)
from .contracts.web import CitationRegistry
from .forward import expand_forward_inputs
from .input import AdapterImageFetcher, collect_input
from .log import current_run_id, log_event, safe_log_text
from .prompt import SYSTEM_PROMPT
from .tools import (
    InvocationParticipantResolver,
    open_zssm_tool_resources,
    resolve_card_urls,
)
from .vision import route_vision

_CITATION_RE = re.compile(r"\[(s[1-9][0-9]*)\]")
_KEYWORD_LINE_RE = re.compile(r"^关键词[:：]\s*(.*)$")
_KEYWORD_SEPARATOR_RE = re.compile(r"\s*(?:\||｜|,|，|、)\s*")
_OUTPUT_LINE_PREFIX_RE = re.compile(r"^(?:#{1,6}\s*|[-*•]\s+|\d+[.)、]\s+)")
_BODY_WHITESPACE_RE = re.compile(r"\s+")
_BODY_CHAR_LIMIT = 500
_RUN_LIMITERS: WeakKeyDictionary[
    asyncio.AbstractEventLoop, dict[int, asyncio.Semaphore]
] = WeakKeyDictionary()


class AllImagesFailedError(RuntimeError):
    """No requested image produced usable primary-model input."""


def _run_limiter(max_concurrent_runs: int) -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    by_capacity = _RUN_LIMITERS.setdefault(loop, {})
    limiter = by_capacity.get(max_concurrent_runs)
    if limiter is None:
        limiter = asyncio.Semaphore(max_concurrent_runs)
        by_capacity[max_concurrent_runs] = limiter
    return limiter


async def snapshot_history_high_water(
    session: Session,
    current: UniMessage,
    started_at: datetime,
) -> int:
    """Freeze the latest row recorded before this matcher continues."""

    del current
    whereclause = filter_statement(
        session=session,
        filter_user=False,
        exclude_user_ids=(session.self_id,),
        time_stop=started_at,
        types=("message",),
    )
    statement = (
        select(func.max(MessageRecord.id))
        .where(*whereclause)
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .join(BotModel, BotModel.id == SessionModel.bot_persist_id)
        .join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
        .join(UserModel, UserModel.id == SessionModel.user_persist_id)
    )
    async with get_session() as database:
        maximum = await database.scalar(statement)
    return 0 if maximum is None else int(maximum)


def _normalize_keywords(value: str) -> str:
    keywords = tuple(
        dict.fromkeys(
            item.strip() for item in _KEYWORD_SEPARATOR_RE.split(value) if item.strip()
        )
    )
    return " | ".join(keywords[:6]) or "综合"


def _normalize_body(lines: list[str]) -> str:
    normalized: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("```"):
            continue
        line = _OUTPUT_LINE_PREFIX_RE.sub("", line, count=1).strip()
        if line:
            normalized.append(line)

    body = _BODY_WHITESPACE_RE.sub(" ", " ".join(normalized)).strip()
    if not body:
        return "（抱歉，我现在还不会这个）"
    if len(body) <= _BODY_CHAR_LIMIT:
        return body

    clipped = body[:_BODY_CHAR_LIMIT]
    boundary = max(clipped.rfind(mark) for mark in "。！？!?")
    if boundary >= _BODY_CHAR_LIMIT // 2:
        return clipped[: boundary + 1]
    return clipped[:-1].rstrip("，,；;：:、 ") + "…"


def _safe_answer(answer: str, citations: CitationRegistry) -> str:
    answer = answer.strip()

    def replace(match: re.Match[str]) -> str:
        return match.group(0) if citations.get(match.group(1)) is not None else ""

    answer = _CITATION_RE.sub(replace, answer).strip()
    keyword_value = ""
    body_lines: list[str] = []
    for line in answer.splitlines():
        if not keyword_value and (match := _KEYWORD_LINE_RE.match(line.strip())):
            keyword_value = match.group(1)
            continue
        body_lines.append(line)

    keywords = _normalize_keywords(keyword_value)
    body = _normalize_body(body_lines)
    return f"关键词：{keywords}\n\n{body}"


def _append_image_processing_notices(
    answer: str,
    *,
    omitted_images: int,
    max_images: int,
    partial_success: bool,
) -> str:
    notices: list[str] = []
    if omitted_images:
        notices.append(
            "图片处理提示：普通图片输入超过上限，仅处理前 "
            f"{max_images} 张，其余 {omitted_images} 张普通图片未处理。"
        )
    if partial_success:
        notices.append("图片处理提示：部分图片处理失败，以上解释仅基于成功处理的内容。")
    return f"{answer} {" ".join(notices)}" if notices else answer


def _tool_trace(result: AgentRunResult) -> tuple[ToolDisplayEntry, ...]:
    return tuple(
        ToolDisplayEntry(
            name=item.name,
            summary=item.summary,
            status=(
                ToolDisplayStatus.SUCCESS if item.success else ToolDisplayStatus.ERROR
            ),
            elapsed=item.elapsed,
        )
        for item in result.trace.tool_calls
    )


async def run_zssm(
    *,
    bot: Bot,
    event: Event,
    session: Session,
    current: UniMessage,
    content: UniMessage,
    quoted: UniMessage | None,
    config: ZssmConfig,
    service: LLMService,
    model_alias: str | None = None,
    adapter_image_fetcher: AdapterImageFetcher | None = None,
) -> RenderModel:
    """Run one isolated ZSSM agent invocation and return renderer input."""

    current_copy = current.copy()
    content_copy = content.copy()
    quoted_copy = quoted.copy() if quoted is not None else None
    started_at = datetime.now(UTC)
    started = perf_counter()
    primary = (
        service.get_model(model_alias)
        if model_alias is not None
        else await service.get_active_model()
    ).require_capability(ModelCapability.TOOLS)
    primary_alias = primary.alias

    outer_limiter = _run_limiter(config.max_concurrent_runs)
    wait_started = perf_counter()
    async with outer_limiter:
        log_event(
            "INFO",
            "ZSSM",
            f"<b>run slot acquired</> | "
            f"wait=<y>{(perf_counter() - wait_started) * 1000:.1f}ms</> "
            f"capacity=<c>{config.max_concurrent_runs}</> "
            f"model=<g>{safe_log_text(primary_alias)}</>",
        )
        forward_started = perf_counter()
        expanded_content, expanded_quoted = await expand_forward_inputs(
            content_copy,
            quoted_copy,
            bot=bot,
            event=event,
            config=config.forwards,
        )
        log_event(
            "DEBUG",
            "ZSSM",
            f"<b>forward expansion completed</> | "
            f"elapsed=<c>{(perf_counter() - forward_started) * 1000:.1f}ms</> "
            f"quoted=<y>{str(expanded_quoted is not None).lower()}</>",
        )
        participant_resolver = InvocationParticipantResolver(
            bot,
            session,
            config.participants,
        )
        collected = await collect_input(
            expanded_content,
            expanded_quoted,
            invoker_raw_id=session.user.id,
            participant_resolver=participant_resolver,
            config=config.images,
            card_url_resolver=partial(resolve_card_urls, config=config.fetch_page),
        )
        history_high_water = await snapshot_history_high_water(
            session,
            current_copy,
            started_at,
        )
        log_event(
            "INFO",
            "ZSSM",
            f"<b>input ready</> | text_chars=<c>{len(collected.prompt_text)}</> "
            f"images=<c>{len(collected.images)}</> "
            f"deferred_images=<c>{len(collected.deferred_images)}</> "
            f"participants=<c>{len(collected.participant_aliases)}</>",
        )
        routed = await route_vision(
            collected,
            primary_model=primary_alias,
            vision_model=config.vision_model,
            config=config.images,
            llm_service=service,
            adapter_image_fetcher=adapter_image_fetcher,
        )
        if routed.primary is None:
            raise AllImagesFailedError

        invocation = ZssmInvocationFacts(
            started_at=started_at,
            active_model=primary_alias,
            invoker_alias=collected.participant_aliases[0],
        )
        async with open_zssm_tool_resources(
            config=config,
            session=session,
            participant_resolver=participant_resolver,
            history_high_water=history_high_water,
            invocation=invocation,
            llm_service=service,
            deferred_images=collected.deferred_images,
            adapter_image_fetcher=adapter_image_fetcher,
        ) as resources:
            max_tool_images = max(
                config.images.max_tool_count,
                config.source_images.max_pages_per_run,
            )
            limits = AgentLimits(
                max_model_calls=config.max_agent_model_calls,
                max_tool_calls=config.max_agent_tool_calls,
                max_parallel_tools=config.max_agent_parallel_tools,
                max_tool_images=max_tool_images,
                max_tool_image_bytes=(
                    config.images.max_payload_bytes * max_tool_images
                ),
                total_timeout_seconds=config.agent_timeout_seconds,
                max_output_tokens=config.max_output_tokens,
            )
            result = await service.run_agent(
                routed.primary,
                tools=resources.tools,
                system_prompt=SYSTEM_PROMPT,
                model=primary_alias,
                limits=limits,
                reasoning_effort=config.agent_reasoning_effort,
                correlation_id=current_run_id.get(),
            )
            answer = _safe_answer(result.output, resources.citations)
            answer = _append_image_processing_notices(
                answer,
                omitted_images=collected.omitted_images,
                max_images=config.images.max_count,
                partial_success=routed.stats.partial_success,
            )
            trace = _tool_trace(result)
            primary_usage = ModelStageUsage(
                model_alias=result.model_alias,
                model_id=result.model_id,
                calls=result.model_call_count,
                usage_calls=result.model_call_count,
                usage=result.usage,
                elapsed=sum(item.elapsed for item in result.trace.model_calls),
            )
            total_elapsed = perf_counter() - started
            stats = RunStatistics(
                total_elapsed=total_elapsed,
                primary_usage=primary_usage,
                vision_usage=routed.stage_usage,
                images=routed.stats,
                tool_calls=result.tool_call_count,
                tool_failures=sum(not item.success for item in result.trace.tool_calls),
                tool_elapsed=sum(item.elapsed for item in result.trace.tool_calls),
                tool_images=sum(item.image_count for item in result.trace.tool_calls),
                tool_image_bytes=sum(
                    item.image_bytes for item in result.trace.tool_calls
                ),
            )
            sources = tuple(
                SourceEntry.from_citation(citation)
                for citation in resources.citations.used_citations()
            )
            log_event(
                "SUCCESS",
                "ZSSM",
                f"<g><b>assembled</b></> | elapsed=<c>{total_elapsed * 1000:.1f}ms</> "
                f"model_calls=<c>{result.model_call_count}</> "
                f"tools=<c>{result.tool_call_count}</> "
                f"tool_failures=<y>{stats.tool_failures}</> "
                f"images=<c>{routed.stats.prepared}/{routed.stats.requested}</> "
                f"sources=<c>{len(sources)}</> answer_chars=<c>{len(answer)}</>",
            )
            return RenderModel(
                answer=answer,
                current=current_copy,
                quoted=quoted_copy,
                sources=sources,
                trace=trace,
                stats=stats,
            )


__all__ = [
    "AllImagesFailedError",
    "run_zssm",
    "snapshot_history_high_water",
]
