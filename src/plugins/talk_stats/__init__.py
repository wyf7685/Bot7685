from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
from nonebot_plugin_alconna import Alconna, Args, Option, UniMessage, on_alconna
from nonebot_plugin_uninfo import Uninfo

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .query import query_session
from .render import render_my

alc = Alconna(
    "talk_stats",
    Option("my|--my", dest="my"),
    Option("days|--days|-d", Args["days?#天数", int]),
)


matcher = on_alconna(alc, permission=TrustedUser())
matcher.shortcut(
    r"我的水群瓷砖",
    {"command": "talk_stats --my {*}"},
)


@matcher.assign("my")
async def assign_my(session: Uninfo, days: int = 30) -> None:
    data = await query_session(session, days)
    raw = await render_my(data, days)
    await UniMessage.image(raw=raw).finish(reply_to=True)


# @matcher.handle()
# async def handle(session: Uninfo, days: int = 7) -> None:
#     data = await query_scene(session, days)
