import httpx
from nonebot import require
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    Alconna,
    CommandMeta,
    Match,
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
        Option("r18"),
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
async def _(r18: Match) -> None:
    base_url = "https://api.lolicon.app/setu"
    params = {"r18": int(r18.available)}

    async with httpx.AsyncClient() as client:
        resp = await client.get(base_url, params=params)
        if resp.status_code != 200:
            await UniMessage.text("接口请求失败").finish(reply_to=True)
        data = resp.json()
        if data["code"] != 0:
            await UniMessage.text(f"接口错误: {data["msg"]}").finish(reply_to=True)

        resp = await client.get(data["data"][0]["url"])
        if resp.status_code != 200:
            await UniMessage.text("图片获取失败").finish(reply_to=True)
        data = resp.read()

    await UniMessage.image(raw=data).finish(reply_to=True)
