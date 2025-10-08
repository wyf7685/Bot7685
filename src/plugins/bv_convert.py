import json
from typing import TYPE_CHECKING, Annotated

from nonebot import on_startswith, require
from nonebot.params import EventPlainText
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

if TYPE_CHECKING:
    from nonebot.adapters.onebot.v11 import MessageEvent
    from nonebot.typing import T_State

__plugin_meta__ = PluginMetadata(
    name="bv_convert",
    description="BV号转换链接",
    usage="BV1xxxxxxxxx",
    type="application",
)


def _check_bv1(plain: Annotated[str, EventPlainText()]) -> bool:
    return len(plain) == 12 and all(i.isalnum() for i in plain[3:])


bv1 = on_startswith("BV1", rule=_check_bv1, permission=TrustedUser())


@bv1.handle()
async def handle_bv1(plain: Annotated[str, EventPlainText()]) -> None:
    await (
        UniMessage.text("https://www.bilibili.com/video/")
        .text(plain)
        .finish(reply_to=True)
    )


def _check_bili_card(event: MessageEvent, state: T_State) -> bool:
    segs = event.get_message().include("json")
    if not segs:
        return False

    try:
        data: dict = json.loads(segs[0].data["data"])
    except (json.JSONDecodeError, KeyError):
        return False

    if data.get("app") != "com.tencent.miniapp_01":
        return False

    try:
        detail = data["meta"]["detail_1"]
        link = detail["qqdocurl"]
    except KeyError:
        return False

    if not link:
        return False

    state["link"] = link
    return True
