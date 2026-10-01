import asyncio
import contextlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Final

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import (
    SupportScope,
    get_message_id,
    get_target,
    message_reaction,
)

from .log import error_context, log_event, safe_log_text

_REACTION_MILESTONES: Final[tuple[tuple[float, str], ...]] = (
    (15.0, "424"),
    (45.0, "30"),
    (90.0, "373"),
)


def _should_react(bot: Bot, event: Event) -> bool:
    try:
        target = get_target(event, bot)
        get_message_id(event, bot)
    except Exception as error:
        error.add_note("ZSSM progress reaction: determine target eligibility")
        log_event(
            "WARNING",
            "ZSSM::Reaction",
            f"<y>target lookup failed</> diagnostic=<r>{error_context(error)}</>",
        )
        return False
    return not target.private and target.scope == SupportScope.qq_client


async def _safe_reaction(
    bot: Bot,
    event: Event,
    emoji: str,
    *,
    delete: bool = False,
) -> None:
    try:
        await message_reaction(emoji=emoji, event=event, bot=bot, delete=delete)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        operation = "remove" if delete else "add"
        error.add_note(
            f"ZSSM progress reaction: {operation} marker={safe_log_text(emoji)}"
        )
        log_event(
            "WARNING",
            "ZSSM::Reaction",
            f"<y>marker {operation} failed</> diagnostic=<r>{error_context(error)}</>",
        )


async def _run_reaction_timeline(bot: Bot, event: Event) -> None:
    active_emoji: str | None = None
    previous_at = 0.0
    try:
        for at_seconds, emoji in _REACTION_MILESTONES:
            await asyncio.sleep(at_seconds - previous_at)
            if active_emoji is not None:
                await _safe_reaction(bot, event, active_emoji, delete=True)
            await _safe_reaction(bot, event, emoji)
            active_emoji = emoji
            previous_at = at_seconds
        await asyncio.Event().wait()
    finally:
        if active_emoji is not None:
            await _safe_reaction(bot, event, active_emoji, delete=True)


@asynccontextmanager
async def zssm_reaction_timeline(bot: Bot, event: Event) -> AsyncGenerator[None]:
    """Run and reliably clean up ZSSM-owned progress reactions."""

    if not _should_react(bot, event):
        yield
        return

    task = asyncio.create_task(
        _run_reaction_timeline(bot, event),
        name="zssm-reaction-timeline",
    )
    try:
        yield
    finally:
        task.cancel()
        try:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        except Exception as error:
            error.add_note("ZSSM stage: clean up progress-reaction timeline")
            log_event(
                "ERROR",
                "ZSSM::Reaction",
                f"<r>timeline failed</> diagnostic=<r>{error_context(error)}</>",
            )
            raise


__all__ = ["zssm_reaction_timeline"]
