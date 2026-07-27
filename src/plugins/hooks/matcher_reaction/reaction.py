import contextlib

from nonebot import get_driver
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor, run_preprocessor
from nonebot_plugin_alconna import (
    SupportScope,
    get_message_id,
    get_target,
    message_reaction,
)

from . import store

COFFEE = "60"
TADA = "144"
SHIVER = "41"

driver = get_driver()
in_progress: dict[str, int] = {}


def should_react(bot: Bot, event: Event) -> bool:
    try:
        target = get_target(event, bot)
    except NotImplementedError:
        return False
    try:
        get_message_id(event, bot)
    except Exception:
        return False

    return not target.private and target.scope == SupportScope.qq_client


async def safe_reaction(
    bot: Bot,
    event: Event,
    emoji: str,
    delete: bool = False,
) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot, delete=delete)


async def cache_exception(event: Event, matcher: Matcher, exc: Exception) -> None:
    with contextlib.suppress(Exception):
        await store.add(get_message_id(event), matcher, exc)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: Event) -> None:
    if should_react(bot, event):
        message_id = get_message_id(event)
        in_progress[message_id] = in_progress.get(message_id, 0) + 1
        driver.task_group.start_soon(safe_reaction, bot, event, COFFEE)


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    exception: Exception | None,
) -> None:
    if should_react(bot, event):
        emoji = TADA if exception is None else SHIVER
        driver.task_group.start_soon(safe_reaction, bot, event, emoji)
        if exception is not None:
            driver.task_group.start_soon(cache_exception, event, matcher, exception)

        message_id = get_message_id(event)
        in_progress[message_id] = in_progress.get(message_id, 1) - 1
        if in_progress[message_id] <= 0:
            del in_progress[message_id]
            await safe_reaction(bot, event, COFFEE, delete=True)
