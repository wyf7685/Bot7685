import asyncio
import hashlib
import random
from pathlib import Path
from typing import Literal, assert_never

from nonebot import on_message, require
from nonebot.adapters import Bot, Event
from nonebot.utils import run_sync

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Image, UniMessage, UniMsg, image_fetch
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_localstore import get_plugin_cache_dir

require("src.service.cache")
require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser
from src.service.cache import get_cache

from .detector import ScreenDetector

ROOT = Path(__file__).parent.resolve()
CACHE_DIR = get_plugin_cache_dir()
_detector = ScreenDetector()
_cache = get_cache[bool]("screen_detector", pickle=True)


@run_sync
def _detect_image(path: Path) -> bool:
    try:
        result = _detector.detect(path)
        return result.get("result", "normal") == "screen_photo"
    except Exception:
        return False


async def _detect_one(event: Event, bot: Bot, image: Image) -> bool:
    if image.sticker:
        return False

    if (
        image.id is not None
        and (cached := await _cache.get(f"id:{image.id}", default=None)) is not None
    ):
        return cached

    raw = await image_fetch(event, bot, {}, image)
    if raw is None:
        return False

    info = fleep.get(raw[:128])
    if not info.extensions:
        return False

    raw_hash = hashlib.sha256(raw).hexdigest()
    cached = await _cache.get(f"hash:{raw_hash}", default=None)
    if cached is not None:
        return cached

    image_path = CACHE_DIR / f"{raw_hash}.{info.extensions[0]}"
    image_path.write_bytes(raw)
    try:
        result = await _detect_image(image_path)
    finally:
        image_path.unlink(missing_ok=True)

    if image.id is not None:
        await _cache.set(f"id:{image.id}", result, ttl=3600 * 24 * 7)
    await _cache.set(f"hash:{raw_hash}", result, ttl=3600 * 24 * 7)

    return result


async def _detect_screen_rule(event: Event, bot: Bot, msg: UniMsg) -> bool:
    if not (images := msg[Image]):
        return False
    if len(images) == 1:
        return await _detect_one(event, bot, images[0])
    coros = (_detect_one(event, bot, image) for image in images)
    return any(await asyncio.gather(*coros))


matcher = on_message(rule=_detect_screen_rule, permission=TrustedUser())


reply_msgs: list[tuple[Literal["text", "image"], str]] = [
    ("text", "还在拍屏还在拍屏"),
    ("text", "拍屏几几小！"),
    ("image", "images/1.jpg"),
]


def _get_reply_message() -> UniMessage:
    match random.choice(reply_msgs):
        case ("text", msg):
            return UniMessage.text(msg)
        case ("image", path):
            return UniMessage.image(raw=(ROOT / path).read_bytes())
        case x:
            assert_never(x)


@matcher.handle()
async def handle_screen_photo() -> None:
    await _get_reply_message().finish(reply_to=True)
