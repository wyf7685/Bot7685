import random
from pathlib import Path

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, UniMessage

images = list((Path(__file__).parent / "images").iterdir())
matcher = (
    Command("测试 [...args]")
    .action(lambda: UniMessage.image(raw=random.choice(images).read_bytes()))
    .build(priority=2)
)
