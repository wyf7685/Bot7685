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


async def _check_bv1(plain: Annotated[str, EventPlainText()]) -> bool:
    return len(plain) == 12 and all(i.isalnum() for i in plain[3:])


bv1 = on_startswith("BV1", rule=_check_bv1, permission=TrustedUser())


@bv1.handle()
async def handle_bv1(plain: Annotated[str, EventPlainText()]) -> None:
    await (
        UniMessage.text("https://www.bilibili.com/video/")
        .text(plain)
        .finish(reply_to=True)
    )
