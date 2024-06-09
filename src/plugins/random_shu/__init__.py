from random import Random
from pathlib import Path

from nonebot import on_fullmatch, require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna.uniseg import UniMessage

random = Random()
image_fps = list((Path(__file__).parent.resolve() / "images").iterdir())


@on_fullmatch("抽黍泡泡").handle()
async def _():
    fp = random.choice(image_fps)
    await UniMessage.image(raw=fp.read_bytes(), name=fp.name).send()
