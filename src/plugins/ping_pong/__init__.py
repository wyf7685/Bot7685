import pathlib
import random

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, UniMessage

ping = Command("ping [...args]").build(priority=10)
root = pathlib.Path(__file__).resolve().parent


@ping.handle()
async def _() -> None:
    file = random.choice(list(root.glob("*.jpg")))
    await UniMessage.text("pong").image(raw=file.read_bytes()).send(reply_to=True)
