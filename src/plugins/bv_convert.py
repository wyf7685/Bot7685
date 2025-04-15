from typing import Annotated

from nonebot import on_startswith, require
from nonebot.params import EventPlainText
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

__plugin_meta__ = PluginMetadata(
    name="bv_convert",
    description="BV号转换链接",
    usage="BV1xxxxxxxxx",
    type="application",
)


def _check(plain: Annotated[str, EventPlainText()]) -> bool:
    return len(plain) == 12 and all(i.isalnum() for i in plain[3:])


matcher = on_startswith(
    "BV1",
    rule=_check,
    permission=TrustedUser(),
)


@matcher.handle()
async def _(plain: Annotated[str, EventPlainText()]) -> None:
    await UniMessage.text("https://www.bilibili.com/").text(plain).finish(reply_to=True)
