import asyncio
import hashlib
from pathlib import Path

from nonebot import logger, on_message, require
from nonebot.adapters import Bot, Event

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_uninfo")
from nonebot_plugin_alconna import Image, UniMsg, image_fetch, message_reaction
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_localstore import get_plugin_cache_dir
from nonebot_plugin_uninfo import SupportScope, Uninfo

require("src.service.cache")
from src.service.cache import get_cache

from .api import detector_client
from .config import plugin_config

ROOT = Path(__file__).parent.resolve()
CACHE_DIR = get_plugin_cache_dir()
DETECTION_CACHE_TTL = 3600 * 24
VALID_MIMES = {"image/jpeg", "image/png", "image/webp"}
_cache = get_cache[bool]("screen_detector_v2")


async def _cache_result_by_id(id: str | None, result: bool) -> None:
    if id is not None:
        await _cache.set(f"id:{id}", result, ttl=DETECTION_CACHE_TTL)


async def _cache_result_by_hash(raw_hash: str, result: bool) -> None:
    await _cache.set(f"hash:{raw_hash}", result, ttl=DETECTION_CACHE_TTL)


async def _detect_one(event: Event, bot: Bot, image: Image) -> bool:
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
        await _cache_result_by_id(image.id, result)
        return result

    raw = await image_fetch(event, bot, {}, image)
    if raw is None:
        await _cache_result_by_id(image.id, False)
        return False

    raw_hash = hashlib.sha256(raw).hexdigest()

    info = fleep.get(raw[:128])
    if not info.extensions or not info.mimes or info.mimes[0] not in VALID_MIMES:
        await _cache_result_by_id(image.id, False)
        await _cache_result_by_hash(raw_hash, False)
        return False

    cached = await _cache.get(f"hash:{raw_hash}")
    if cached is not None:
        await _cache_result_by_id(image.id, cached)
        return cached

    result = await detector_client.detect_screen_from_upload(
        raw, info.extensions[0], info.mimes[0]
    )
    if result is None:
        return False

    await _cache_result_by_id(image.id, result)
    await _cache_result_by_hash(raw_hash, result)
    return result


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
        return await _detect_one(event, bot, images[0])
    coros = (_detect_one(event, bot, image) for image in images)
    return any(await asyncio.gather(*coros))


if plugin_config.api_base_url:
    logger.debug(
        f"Screen Detector plugin loaded with API base URL: {plugin_config.api_base_url}"
    )
    matcher = on_message(rule=_detect_screen_rule)

    @matcher.handle()
    async def handle_screen_photo() -> None:
        await message_reaction("424")
else:
    logger.warning(
        "Screen Detector plugin loaded without API base URL. "
        "Detection will be disabled."
    )
