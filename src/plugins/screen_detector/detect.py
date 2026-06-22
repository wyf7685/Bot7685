import asyncio
import contextlib
import functools
import hashlib
from collections.abc import Awaitable

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.message import event_preprocessor
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, image_fetch, message_reaction
from nonebot_plugin_alconna.uniseg.params import _uni_msg as get_uni_msg
from nonebot_plugin_alconna.uniseg.utils import fleep
from nonebot_plugin_uninfo import Session, SupportScope, get_session

from src.bootstrap.params import T_DependencyCache, call_as_dependent
from src.service.cache import get_cache
from src.service.task import call_soon

from .api import DetectResult, detector_client
from .config import plugin_config
from .reaction import store_image_id

DETECTION_CACHE_TTL = 3600 * 24
VALID_MIMES = {"image/jpeg", "image/png", "image/webp"}
_cache = get_cache("screen:result", bool)


@functools.lru_cache(maxsize=16)
def _id_key(id: str) -> str:
    return f"id:{hashlib.sha256(id.encode()).hexdigest()}"


async def _cache_result(
    event: Event,
    result: DetectResult | bool,
    id: str | None,
    raw_hash: str | None = None,
) -> bool:
    is_screen = result.is_screen if isinstance(result, DetectResult) else result
    coros: list[Awaitable[object]] = []
    if id:
        coros.append(_cache.set(_id_key(id), is_screen, ttl=DETECTION_CACHE_TTL))
    if raw_hash:
        coros.append(_cache.set(f"hash:{raw_hash}", is_screen, ttl=DETECTION_CACHE_TTL))
    if isinstance(result, DetectResult):
        coros.append(store_image_id(event, result.image_id, is_screen))
    if coros:
        await asyncio.gather(*coros)
    return is_screen


async def detect_one(bot: Bot, event: Event, image: Image) -> bool:
    if image.sticker:
        return False

    if image.id is not None:
        cached = await _cache.get(_id_key(image.id))
        if cached is not None:
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


@event_preprocessor
async def detect_screen_photo(
    bot: Bot,
    event: Event,
    state: T_State,
    stack: contextlib.AsyncExitStack | None = None,
    dependency_cache: T_DependencyCache | None = None,
) -> None:
    if not plugin_config.enabled_scenes:
        return

    unimsg = await call_as_dependent(
        get_uni_msg, stack, dependency_cache, bot, event, state
    )

    if not (images := unimsg[Image]):
        return

    try:
        session: Session | None = await call_as_dependent(
            get_session, stack, dependency_cache, bot, event
        )
    except Exception:
        session = None

    if (
        session is None
        or session.scope != SupportScope.qq_client
        or session.scene.is_private
        or session.scene.id not in plugin_config.enabled_scenes
    ):
        return

    async def detect() -> bool:
        if len(images) == 1:
            return await detect_one(bot, event, images[0])
        coros = (detect_one(bot, event, image) for image in images)
        return any(await asyncio.gather(*coros))

    async def detect_and_react() -> None:
        try:
            is_screen = await detect()
        except Exception:
            logger.opt(exception=True).warning("Failed to detect screen")
            return

        if is_screen:
            with contextlib.suppress(Exception):
                await message_reaction("424", None, event, bot)

    call_soon(detect_and_react)
