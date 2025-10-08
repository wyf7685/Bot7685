import contextlib

from nonebot import get_driver, require
from nonebot.message import run_postprocessor, run_preprocessor

require("nonebot_plugin_alconna")
from typing import TYPE_CHECKING

from nonebot_plugin_alconna import message_reaction

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import Bot, MessageEvent

driver = get_driver()


async def wrapper(bot: Bot, event: MessageEvent, emoji: str) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji, None, event, bot)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: MessageEvent) -> None:
    driver.task_group.start_soon(wrapper, bot, event, "60")  # coffee


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: MessageEvent,
    exception: Exception | None,
) -> None:
    emoji = "144" if exception is None else "10060"  # 🎉 : ❌
    driver.task_group.start_soon(wrapper, bot, event, emoji)
