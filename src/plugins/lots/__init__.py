from nonebot import require
from nonebot.adapters import Event
from nonebot.params import Depends

require("nonebot_plugin_alconna")
from arclet.alconna import Alconna, Args, Arparma
from nonebot_plugin_alconna import AlconnaMatches, At, UniMessage, on_alconna

from .lots_data import get_lots_msg

lots = on_alconna(Alconna("御神签", Args["target?", At]))


def LotsTarget():
    def lots_target(event: Event, result: Arparma = AlconnaMatches()) -> str:
        uin = event.get_user_id()
        if target := result.query[At]("target"):
            uin = target.target
        return uin

    return Depends(lots_target)


@lots.handle()
async def _(target: str = LotsTarget()):
    await UniMessage.text(get_lots_msg(target)).send()
