from typing import Annotated

from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import AlcMatches
from nonebot_plugin_alconna.uniseg import At


def _lots_target() -> str:
    async def lots_target(event: Event, result: AlcMatches) -> str:
        uin = event.get_user_id()
        if target := result.query[At]("target"):
            uin = target.target
        return uin

    return Depends(lots_target)


LotsTarget = Annotated[str, _lots_target()]
