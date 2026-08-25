from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import (
    SupportScope,
    get_message_id,
    get_target,
    message_reaction,
)

_REACTION_MILESTONES: Final[tuple[tuple[float, str], ...]] = (
    (15.0, "424"),
    (45.0, "30"),
    (90.0, "373"),
)


def _should_react(bot: Bot, event: Event) -> bool:
    try:
        target = get_target(event, bot)
        get_message_id(event, bot)
    except Exception:
        return False
    return not target.private and target.scope == SupportScope.qq_client


async def _safe_reaction(
    bot: Bot,
    event: Event,
    emoji: str,
    *,
    delete: bool = False,
) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot, delete=delete)


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
async def zssm_reaction_timeline(bot: Bot, event: Event) -> AsyncIterator[None]:
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
        with contextlib.suppress(asyncio.CancelledError):
            await task


__all__ = ["zssm_reaction_timeline"]
