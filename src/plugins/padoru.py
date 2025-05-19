from pathlib import Path

from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command, Voice

if (PADORU_MP3 := Path("data/padoru.mp3")).exists():
    matcher = (
        Command("padoru", help_text="padoru")
        .action(lambda: Voice(raw=PADORU_MP3.read_bytes()))
        .build()
    )
