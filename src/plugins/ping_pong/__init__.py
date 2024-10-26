import pathlib
import random

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, UniMessage

Command("ping").action(
    func=lambda: UniMessage.text("pong").image(
        raw=random.choice(
            list(pathlib.Path(__file__).resolve().parent.glob("*.jpg"))
        ).read_bytes()
    )
).build()
