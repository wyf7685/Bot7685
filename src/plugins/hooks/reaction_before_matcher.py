import contextlib

from nonebot import require
from nonebot.adapters import milky
from nonebot.adapters.onebot import v11 as ob11
from nonebot.message import run_postprocessor, run_preprocessor

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import message_reaction

from src.utils import EventTaskGroup

Bot = milky.Bot | ob11.Bot
MessageEvent = milky.MessageEvent | ob11.MessageEvent


async def safe_reaction(bot: Bot, event: MessageEvent, emoji: str) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot)


@run_preprocessor
async def reaction_before_matcher(
    bot: Bot,
    event: MessageEvent,
    tg: EventTaskGroup,
) -> None:
    tg.start_soon(safe_reaction, bot, event, "60")  # coffee


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: MessageEvent,
    exception: Exception | None,
    tg: EventTaskGroup,
) -> None:
    emoji = "144" if exception is None else "10060"  # 🎉/❌
    tg.start_soon(safe_reaction, bot, event, emoji)
