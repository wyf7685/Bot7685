import httpx
from nonebot import require
from nonebot.adapters import Bot
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    Alconna,
    Arparma,
    CommandMeta,
    Image,
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
        Option("r18|--r18", help_text="启用 R18"),
        Option("noai|--noai", help_text="排除 AI 作品"),
        meta=CommandMeta(
            "涩图",
            "setu [--r18] [--noai]",
            "setu\nsetu r18",
        ),
    ),
    rule=_check,
    aliases={"色图", "涩图", "来张涩图", "来张色图"},
    use_cmd_start=True,
)


@setu.handle()
async def _(arp: Arparma) -> None:
    base_url = "https://api.lolicon.app/setu/v2"
    params = {"r18": int("r18" in arp.options), "excludeAI": "noai" in arp.options}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(base_url, json=params)
        except Exception as err:
            await UniMessage.text(f"接口请求出错: {err}").finish(reply_to=True)

        if resp.status_code != 200:
            await UniMessage.text("接口请求失败").finish(reply_to=True)

        data = resp.json()
        if data["error"]:
            await UniMessage.text(f"接口错误: {data['error']}").finish(reply_to=True)

        img_data = data["data"][0]
        img = str(img_data["urls"]["original"])

        try:
            resp = await client.get(img)
        except Exception as err:
            await UniMessage.text(f"图片请求出错: {err}").finish(reply_to=True)

        if resp.status_code == 200:
            img = Image(raw=resp.read())
        else:
            await UniMessage.text(f"图片获取失败: {resp.status_code}").finish(
                reply_to=True
            )

    r18 = "是" if img_data["r18"] else "否"
    ai_type = {0: "未知", 1: "否", 2: "是"}.get(img_data["aiType"])
    description = (
        f"PID: {img_data['pid']}\n"
        f"标题: {img_data['title']}\n"
        f"作者: {img_data['author']}\n"
        f"R18: {r18}\n"
        f"AI: {ai_type}\n"
        f"标签: {', '.join(img_data['tags'])}\n"
    )
    await (UniMessage.text(description) + img).finish(reply_to=True)
