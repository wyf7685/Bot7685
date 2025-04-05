import random
from pathlib import Path

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, UniMessage

__plugin_meta__ = PluginMetadata(
    name="random_neuro",
    description="随机 Neuro/Evil",
    usage="发送 /随机neuro 或 /随机evil",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

image_dir = Path("data/random_neuro")
neuro = list((image_dir / "neuro").iterdir())
evil = list((image_dir / "evil").iterdir())


@(Command("随机neuro [...args]").build(priority=10).handle())
async def cmd_neuro() -> None:
    await UniMessage.image(raw=random.choice(neuro).read_bytes()).finish(reply_to=True)


@(Command("随机evil [...args]").build(priority=10).handle())
async def cmd_evil() -> None:
    await UniMessage.image(raw=random.choice(evil).read_bytes()).finish(reply_to=True)
