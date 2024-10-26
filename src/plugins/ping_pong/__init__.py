import pathlib
import random

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage, on_alconna

ping = on_alconna("ping", priority=10)
root = pathlib.Path(__file__).resolve().parent

@ping.handle()
async def _() -> None:
    file = random.choice(list(root.glob("*.jpg")))
    await UniMessage.text("pong").image(raw=file.read_bytes()).finish(reply_to=True)
