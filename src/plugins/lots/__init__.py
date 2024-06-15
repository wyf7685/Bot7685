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

    logger.info(f"bot={bot}, message_id={msgid}, emoji_id={emoji}")

    if msgid is not None:
        try:
            await bot.call_api(
                "set_msg_emoji_like",
                message_id=msgid,
                emoji_id=emoji,
            )
        except Exception as err:
            logger.opt(exception=err).error(f"调用api `set_msg_emoji_like` 失败: {err}")
