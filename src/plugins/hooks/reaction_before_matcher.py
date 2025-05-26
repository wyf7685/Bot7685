import contextlib

from nonebot import get_driver, require
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.message import run_preprocessor

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import message_reaction


async def wrapper(bot: Bot, event: MessageEvent) -> None:
    with contextlib.suppress(Exception):
        await message_reaction("60", None, event, bot)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: MessageEvent) -> None:
    get_driver().task_group.start_soon(wrapper, bot, event)
