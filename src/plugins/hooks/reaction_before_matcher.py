import contextlib

from nonebot import get_driver, require
from nonebot.adapters import Bot, Event
from nonebot.message import run_postprocessor, run_preprocessor

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import SupportScope, get_target, message_reaction

driver = get_driver()


def should_react(bot: Bot, event: Event) -> bool:
    try:
        target = get_target(event, bot)
    except NotImplementedError:
        return False

    return not target.private and target.scope == SupportScope.qq_client


async def safe_reaction(bot: Bot, event: Event, emoji: str) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: Event) -> None:
    if should_react(bot, event):
        driver.task_group.start_soon(safe_reaction, bot, event, "60")  # coffee


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: Event,
    exception: Exception | None,
) -> None:
    if should_react(bot, event):
        emoji = "144" if exception is None else "41"  # 🎉/[发抖]
        driver.task_group.start_soon(safe_reaction, bot, event, emoji)
