import httpx
from nonebot import require
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    Alconna,
    CommandMeta,
    Option,
    UniMessage,
    on_alconna,
)

__plugin_meta__ = PluginMetadata(
    name="tgsetu",
    description="涩图插件",
    usage="setu [r18]",
    type="application",
)


async def _check(bot: Bot) -> bool:
    return bot.type.lower() == "telegram"


setu = on_alconna(
    Alconna(
        "setu",
        Option("r18", help_text="启用 R18"),
        Option("noai", help_text="排除 AI 作品"),
        meta=CommandMeta(
            "涩图",
            "setu [r18]",
            "setu\nsetu r18",
        ),
    ),
    rule=_check,
    aliases={"色图", "涩图", "来张涩图", "来张色图"},
    use_cmd_start=True,
)


@setu.handle()
async def _(state: T_State) -> None:
    state["params"] = {"r18": 0, "noai": False}


@setu.assign("r18")
async def _(state: T_State) -> None:
    state["params"]["r18"] = 1


@setu.assign("noai")
async def _(state: T_State) -> None:
    state["params"]["noai"] = True


@setu.handle()
async def _(state: T_State) -> None:
    base_url = "https://api.lolicon.app/setu/v2"

    async with httpx.AsyncClient() as client:
        resp = await client.post(base_url, json=state["params"])
        if resp.status_code != 200:
            await UniMessage.text("接口请求失败").finish(reply_to=True)

        data = resp.json()
        if data["error"]:
            await UniMessage.text(f"接口错误: {data['error']}").finish(reply_to=True)

        img_data = data["data"][0]
        img_url = img_data["urls"]["original"]

        resp = await client.get(img_url)
        if resp.status_code != 200:
            await UniMessage.text("图片获取失败").finish(reply_to=True)
        img_raw = resp.read()

    await (
        UniMessage.text(f"PID: {img_data['pid']}\n")
        .text(f"标题: {img_data['title']}\n")
        .text(f"作者: {img_data['author']}")
        .text(f"R18: {'是' if img_data['r18'] else '否'}\n")
        .text(f"Tags: {', '.join(img_data['tags'])}\n")
        .image(raw=img_raw)
        .finish(reply_to=True)
    )
