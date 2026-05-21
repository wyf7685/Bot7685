import asyncio
import hashlib

from nonebot import on_message, require
from nonebot.adapters import Bot, Event

require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")
from nonebot_plugin_alconna import Image, UniMsg, image_fetch, message_reaction
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_uninfo import SupportScope, Uninfo

require("src.service.cache")
from src.service.cache import get_cache

from .api import DetectResult, detector_client
from .config import plugin_config
from .reaction import store_image_id

DETECTION_CACHE_TTL = 3600 * 24
VALID_MIMES = {"image/jpeg", "image/png", "image/webp"}
_cache = get_cache("screen_detector:result", bool)


async def _cache_result(
    event: Event,
    result: DetectResult | bool,
    id: str | None,
    raw_hash: str | None = None,
) -> bool:
    is_screen = result.is_screen is True if isinstance(result, DetectResult) else result
    coros = [
        id and _cache.set(f"id:{id}", is_screen, ttl=DETECTION_CACHE_TTL),
        raw_hash and _cache.set(f"hash:{raw_hash}", is_screen, ttl=DETECTION_CACHE_TTL),
        store_image_id(event, result.image_id, is_screen)
        if isinstance(result, DetectResult)
        else None,
    ]
    await asyncio.gather(*(coro for coro in coros if coro))
    return is_screen


async def detect_one(event: Event, bot: Bot, image: Image) -> bool:
    if image.sticker:
        return False

    if (
        image.id is not None
        and (cached := await _cache.get(f"id:{image.id}")) is not None
    ):
        return cached

    if not await detector_client.check_health():
        return False

    if image.url is not None:
        result = await detector_client.detect_screen(image.url)
        if result is None:
            return False
        return await _cache_result(event, result, image.id)

    raw = await image_fetch(event, bot, {}, image)
    if raw is None:
        return await _cache_result(event, False, image.id)

    raw_hash = hashlib.sha256(raw).hexdigest()

    info = fleep.get(raw[:128])
    if not info.extensions or not info.mimes or info.mimes[0] not in VALID_MIMES:
        return await _cache_result(event, False, image.id, raw_hash)

    cached = await _cache.get(f"hash:{raw_hash}")
    if cached is not None:
        return await _cache_result(event, cached, image.id)

    result = await detector_client.detect_screen_from_upload(
        raw, info.extensions[0], info.mimes[0]
    )
    if result is None:
        return False

    return await _cache_result(event, result, image.id, raw_hash)


async def _detect_screen_rule(
    bot: Bot,
    event: Event,
    unimsg: UniMsg,
    session: Uninfo,
) -> bool:
    if session.scope != SupportScope.qq_client or session.scene.is_private:
        return False
    if (
        not plugin_config.enabled_scenes
        or session.scene.id not in plugin_config.enabled_scenes
    ):
        return False
    if not (images := unimsg[Image]):
        return False
    if len(images) == 1:
        return await detect_one(event, bot, images[0])
    coros = (detect_one(event, bot, image) for image in images)
    return any(await asyncio.gather(*coros))


matcher = on_message(rule=_detect_screen_rule)


@matcher.handle()
async def handle_screen_photo() -> None:
    await message_reaction("424")
