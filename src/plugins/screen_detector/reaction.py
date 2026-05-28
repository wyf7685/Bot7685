import contextlib

import anyio
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

    _cache = get_cache("screen:image_id", list[tuple[str, bool]])

    async def store_image_id(event: Event, image_id: str, is_screen: bool) -> None:
        if not isinstance(event, GroupMessageEvent):
            return

        key = f"{event.data.peer_id}:{event.data.message_seq}"
        ids = await _cache.get(key, [])
        if image_id not in ids:
            ids.append((image_id, is_screen))
        await _cache.set(key, ids, ttl=60 * 60 * 12)

    async def _reaction_rule(event: GroupMessageReactionEvent) -> bool:
        if (
            str(event.data.group_id) not in plugin_config.enabled_scenes
            or not event.data.is_add
            or event.data.face_id not in {"10068", "124"}  # ? / OK
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
        if not ids:
            return

        if not await detector_client.check_health():
            return

        async with anyio.create_task_group() as tg:
            for image_id, is_screen in ids:
                if event.data.face_id == "10068":
                    is_screen = not is_screen
                tg.start_soon(detector_client.classify, image_id, is_screen)
