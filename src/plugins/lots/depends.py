from typing import Annotated

from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import AlcMatches
from nonebot_plugin_alconna.uniseg import At


def _msg_id() -> int | None:
    try:
        from nonebot.adapters.onebot.v11 import MessageEvent
    except ImportError:
        MessageEvent = None  # noqa: N806

    def msg_id(event: Event) -> int | None:
        if MessageEvent is not None and isinstance(event, MessageEvent):
            return event.message_id
        return None

    return Depends(msg_id)


def _lots_target() -> str:
    async def lots_target(event: Event, result: AlcMatches) -> str:
        uin = event.get_user_id()
        if target := result.query[At]("target"):
            uin = target.target
        return uin

    return Depends(lots_target)


MsgId = Annotated[int | None, _msg_id()]
LotsTarget = Annotated[str, _lots_target()]
