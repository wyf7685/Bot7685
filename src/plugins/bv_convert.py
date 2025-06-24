import json
from typing import Annotated

from curl_cffi import AsyncSession
from nonebot import on_message, on_startswith, require
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import EventPlainText
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot.typing import T_State
from nonebot_plugin_alconna import UniMessage

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

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
        UniMessage.text("https://www.bilibili.com/video")
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
        preview = detail["preview"]
        link = detail["qqdocurl"]
    except KeyError:
        return False

    if not preview or not link:
        return False

    state["preview"] = preview
    state["link"] = link
    return True


bili_card = on_message(rule=_check_bili_card, permission=TrustedUser())


@bili_card.handle()
async def handle_bili_card(state: T_State) -> None:
    msg = UniMessage.image(url=state["preview"])

    try:
        async with AsyncSession() as session:
            resp = await session.get(state["link"], allow_redirects=False)
            resp.raise_for_status()
            if resp.status_code != 302 or not (url := resp.headers.get("Location")):
                await msg.text(
                    f"链接获取失败: {resp.status_code}",
                ).finish(reply_to=True)
    except Exception as exc:
        await msg.text(f"链接获取失败: {exc!r}").finish(reply_to=True)

    await msg.text(str(url).partition("?")[0]).finish(reply_to=True)
