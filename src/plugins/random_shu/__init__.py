import random
from pathlib import Path
from typing import NoReturn

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, UniMessage

__plugin_meta__ = PluginMetadata(
    name="random_shu",
    description="随机黍泡泡",
    usage="发送 /黍泡泡",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

# 图源: Bilibili@鱼烤箱
images = list((Path(__file__).parent / "images").iterdir())
matcher = Command("黍泡泡 [...args]").build(priority=2)


@matcher.handle()
async def _() -> NoReturn:
    await UniMessage.image(raw=random.choice(images).read_bytes()).finish(reply_to=True)
