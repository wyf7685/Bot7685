import pathlib
import random

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import UniMessage, on_alconna

ping = on_alconna("ping", priority=10)


@ping.handle()
async def _() -> None:
    await (
        UniMessage.text("pong")
        .image(
            raw=random.choice(
                list(pathlib.Path(__file__).resolve().parent.glob("*.jpg"))
            ).read_bytes()
        )
        .finish()
    )
