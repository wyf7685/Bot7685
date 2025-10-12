import contextlib

from nonebot import get_driver, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.message import run_postprocessor, run_preprocessor

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import message_reaction

driver = get_driver()


async def safe_reaction(bot: Bot, event: MessageEvent, emoji: str) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: MessageEvent) -> None:
    driver.task_group.start_soon(safe_reaction, bot, event, "60")  # coffee


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: MessageEvent,
    exception: Exception | None,
) -> None:
    emoji = "144" if exception is None else "10060"  # 🎉/❌
    driver.task_group.start_soon(safe_reaction, bot, event, emoji)
