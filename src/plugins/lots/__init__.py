from nonebot import require
from nonebot.adapters import Event

require("nonebot_plugin_alconna")
from arclet.alconna import Alconna, Args, Arparma
from nonebot_plugin_alconna import AlconnaMatches, At, on_alconna

from .lots_data import get_lots_msg

lots = on_alconna(Alconna("御神签", Args["target?", At]))


@lots.handle()
async def _(event: Event, result: Arparma = AlconnaMatches()):
    uin = event.get_user_id()
    if target := result.query[At]("target"):
        uin = target.target

    await lots.finish(get_lots_msg(uin))
