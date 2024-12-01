import httpx
from nonebot import require
from nonebot.adapters import Bot
from nonebot.exception import ActionFailed, FinishedException
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    Alconna,
    Arparma,
    CommandMeta,
    Option,
    UniMessage,
    on_alconna,
)

__plugin_meta__ = PluginMetadata(
    name="tgsetu",
    description="涩图插件",
    usage="setu [r18] [noai]",
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
            "setu\nsetu r18\nsetu noai",
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
            resp = await client.get(base_url, params=params)
        except Exception as err:
            await UniMessage.text(f"接口请求出错: {err}").finish(reply_to=True)

        if resp.status_code != 200:
            await UniMessage.text("接口请求失败").finish(reply_to=True)

        data = resp.json()
        if data["error"]:
            await UniMessage.text(f"接口错误: {data['error']}").finish(reply_to=True)

        img_data = data["data"][0]
        url = str(img_data["urls"]["original"])

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

    try:
        await UniMessage.text(description).image(url=url).finish(reply_to=True)
    except FinishedException:
        raise
    except ActionFailed:
        await UniMessage.text(f"{description}\n{url}").finish(reply_to=True)
