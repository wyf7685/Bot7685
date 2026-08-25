from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from weakref import WeakKeyDictionary

from nonebot.adapters import Bot
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.orm import BotModel, SceneModel, SessionModel, UserModel
from sqlalchemy import func, select

from src.service.llm import AgentLimits, LLMCapabilityError, LLMService

from .config import ZssmConfig
from .contracts import (
    ModelStageUsage,
    RenderModel,
    RunStatistics,
    SourceEntry,
    ToolDisplayEntry,
    ToolDisplayStatus,
    ZssmInvocationFacts,
)
from .input import collect_input
from .prompt import SYSTEM_PROMPT
from .state import active_model_store
from .tools import (
    InvocationParticipantResolver,
    ZssmToolResources,
    open_zssm_tool_resources,
)
from .vision import VisionRoutingResult, route_vision

_CITATION_RE = re.compile(r"\[(s[1-9][0-9]*)\]")
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


def _safe_answer(answer: str, citations: Any) -> str:
    answer = answer.strip()

    def replace(match: re.Match[str]) -> str:
        return match.group(0) if citations.get(match.group(1)) is not None else ""

    answer = _CITATION_RE.sub(replace, answer).strip()
    if not answer.startswith("关键词："):
        answer = f"关键词：综合\n\n{answer}"
    return answer


def _tool_trace(result: Any) -> tuple[ToolDisplayEntry, ...]:
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
    session: Session,
    current: UniMessage,
    content: UniMessage,
    quoted: UniMessage | None,
    config: ZssmConfig,
    service: LLMService,
    participant_resolver_factory: Callable[
        [Bot, Session, Any], InvocationParticipantResolver
    ] = InvocationParticipantResolver,
    history_snapshot_factory: Callable[
        [Session, UniMessage, datetime], Awaitable[int]
    ] = snapshot_history_high_water,
    tool_resources_factory: Callable[
        ..., AbstractAsyncContextManager[ZssmToolResources]
    ] = open_zssm_tool_resources,
    vision_router: Callable[..., Awaitable[VisionRoutingResult]] = route_vision,
    model_snapshot_factory: Callable[..., Awaitable[Any]] | None = None,
    limiter: asyncio.Semaphore | None = None,
    now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
    clock: Callable[[], float] = perf_counter,
) -> RenderModel:
    """Run one isolated ZSSM agent invocation and return renderer input."""

    current_copy = current.copy()
    content_copy = content.copy()
    quoted_copy = quoted.copy() if quoted is not None else None
    started_at = now_factory()
    started = clock()
    snapshot = model_snapshot_factory or active_model_store.snapshot
    active = await snapshot(config, config.selectable_models)
    active_alias = active.active_model
    handle = service.runtime.resolve(active_alias)
    if not handle.capabilities.tools:
        raise LLMCapabilityError(model_alias=active_alias)

    outer_limiter = limiter or _run_limiter(config.max_concurrent_runs)
    async with outer_limiter:
        participant_resolver = participant_resolver_factory(
            bot,
            session,
            config.participants,
        )
        collected = collect_input(
            content_copy,
            quoted_copy,
            invoker_raw_id=session.user.id,
            participant_resolver=participant_resolver,
            config=config.images,
        )
        history_high_water = await history_snapshot_factory(
            session,
            current_copy,
            started_at,
        )
        routed = await vision_router(
            collected,
            primary_model=active_alias,
            vision_model=config.vision_model,
            config=config.images,
            llm_service=service,
        )
        if routed.primary is None:
            raise AllImagesFailedError

        invocation = ZssmInvocationFacts(
            started_at=started_at,
            active_model=active_alias,
            invoker_alias=collected.participant_aliases[0],
        )
        async with tool_resources_factory(
            config=config,
            session=session,
            participant_resolver=participant_resolver,
            history_high_water=history_high_water,
            invocation=invocation,
        ) as resources:
            limits = AgentLimits(
                max_model_calls=config.max_agent_model_calls,
                max_tool_calls=config.max_agent_tool_calls,
                max_parallel_tools=config.max_agent_parallel_tools,
                total_timeout_seconds=config.agent_timeout_seconds,
                max_output_tokens=config.max_output_tokens,
            )
            result = await service.run_agent(
                routed.primary,
                tools=resources.tools,
                system_prompt=SYSTEM_PROMPT,
                model=active_alias,
                limits=limits,
            )
            answer = _safe_answer(result.output, resources.citations)
            if routed.stats.partial_success:
                answer += (
                    "\n\n图片处理提示：部分图片处理失败，以上回答仅基于成功处理的内容。"
                )
            trace = _tool_trace(result)
            primary_usage = ModelStageUsage(
                model_alias=result.model_alias,
                model_id=result.model_id,
                calls=result.model_call_count,
                usage=result.usage,
                elapsed=sum(item.elapsed for item in result.trace.model_calls),
            )
            stats = RunStatistics(
                total_elapsed=clock() - started,
                primary_usage=primary_usage,
                vision_usage=routed.stage_usage,
                images=routed.stats,
                tool_calls=result.tool_call_count,
                tool_failures=sum(not item.success for item in result.trace.tool_calls),
                tool_elapsed=sum(item.elapsed for item in result.trace.tool_calls),
            )
            sources = tuple(
                SourceEntry.from_citation(citation)
                for citation in resources.citations.used_citations()
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
