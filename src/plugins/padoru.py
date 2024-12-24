from anyio import Path
from nonebot import on_fullmatch
from nonebot.adapters.onebot.v11 import Bot, MessageSegment

PADORU_MP3 = Path("data/padoru.mp3")

padoru = on_fullmatch("padoru")


@padoru.handle()
async def _(_: Bot) -> None:
    data = await PADORU_MP3.read_bytes()
    await padoru.send(MessageSegment.record(data))
