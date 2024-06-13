from typing import Annotated

from nonebot import require
from nonebot.adapters import Bot, Event
from nonebot.log import logger
from nonebot.params import Depends

require("nonebot_plugin_alconna")
from arclet.alconna import Alconna, Args
from nonebot_plugin_alconna import AlcMatches, on_alconna
from nonebot_plugin_alconna.uniseg import At, UniMessage

from .lots_data import get_lots_msg

lots = on_alconna(Alconna("御神签", Args["target?", At]))


def LotsTarget():

    def lots_target(event: Event, result: AlcMatches) -> str:
        uin = event.get_user_id()
        if target := result.query[At]("target"):
            uin = target.target
        return uin

    return Depends(lots_target)


def MsgId():
    try:
        from nonebot.adapters.onebot.v11 import MessageEvent
    except ImportError:
        MessageEvent = None

    def msg_id(event: Event) -> int | None:
        if MessageEvent is not None and isinstance(event, MessageEvent):
            return event.message_id

    return Depends(msg_id)


@lots.handle()
async def _(
    bot: Bot,
    target: Annotated[str, LotsTarget()],
    msgid: Annotated[int | None, MsgId()],
):
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
