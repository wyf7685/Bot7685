import contextlib

from nonebot import require
from nonebot.adapters import Bot
from nonebot.log import logger

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_alconna.uniseg import At, UniMessage

from .depends import LotsTarget, MsgId
from .lots_data import get_lots_msg

lots = on_alconna(Alconna("御神签", Args["target?", At]))


@lots.handle()
async def _(bot: Bot, target: LotsTarget, msgid: MsgId):
    msg, emoji = get_lots_msg(target)
    await UniMessage.text(msg).send(reply_to=True)

    if msgid is not None:
        with contextlib.suppress(Exception):
            await bot.call_api(
                "set_msg_emoji_like",
                message_id=msgid,
                emoji_id=emoji,
            )
            logger.debug(f"{bot=}, {msgid=}, {emoji=}")
