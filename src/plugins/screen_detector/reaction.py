import asyncio
import contextlib

from nonebot import on_type
from nonebot.adapters import Event

from src.service.cache import get_cache

from .api import detector_client
from .config import plugin_config


async def store_image_id(event: Event, image_id: str, is_screen: bool) -> None: ...


with contextlib.suppress(ImportError):
    from nonebot.adapters.milky.event import (
        GroupMessageEvent,
        GroupMessageReactionEvent,
    )

    _cache = get_cache("screen_detector:image_id", list[tuple[str, bool]])

    async def store_image_id(event: Event, image_id: str, is_screen: bool) -> None:
        if not isinstance(event, GroupMessageEvent):
            return

        key = f"{event.data.peer_id}:{event.data.message_seq}"
        ids = await _cache.get(key, [])
        if image_id not in ids:
            ids.append((image_id, is_screen))
        await _cache.set(key, ids, ttl=3600)

    async def _reaction_rule(event: GroupMessageReactionEvent) -> bool:
        if (
            str(event.data.group_id) not in plugin_config.enabled_scenes
            or not event.data.is_add
            or event.data.face_id != "10068"
            or event.data.user_id == event.self_id
        ):
            return False
        key = f"{event.data.group_id}:{event.data.message_seq}"
        return await _cache.exists(key)

    matcher = on_type(GroupMessageReactionEvent, rule=_reaction_rule, priority=5)

    @matcher.handle()
    async def handle_reaction(event: GroupMessageReactionEvent) -> None:
        key = f"{event.data.group_id}:{event.data.message_seq}"
        ids = await _cache.get(key, [])
        if ids and detector_client.is_available:
            await asyncio.gather(
                *(
                    detector_client.update_class(image_id, not is_screen)
                    for image_id, is_screen in ids
                )
            )
