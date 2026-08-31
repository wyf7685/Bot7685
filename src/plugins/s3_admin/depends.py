from typing import Annotated

from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch

from .permission_store import has_permission


def _event_image() -> Image:
    async def event_image(message: UniMsg) -> Image:
        if message.has(Image):
            return message[Image, 0]
        if message.has(Reply):
            reply = message[Reply, 0].msg
            if isinstance(reply, Message):
                attached = await UniMessage.of(reply).attach_reply()
                return await event_image(attached)
        return Matcher.skip()

    return Depends(event_image)


def _event_image_raw() -> bytes:
    async def event_image_raw(
        event: Event,
        bot: Bot,
        state: T_State,
        image: EventImage,
    ) -> bytes:
        raw = await image_fetch(event, bot, state, image)
        if isinstance(raw, bytes):
            return raw
        return Matcher.skip()

    return Depends(event_image_raw)


async def _allow_upload(bot: Bot, event: Event) -> bool:
    return await has_permission(f"{bot.type}:{event.get_user_id()}")


EventImage = Annotated[Image, _event_image()]
EventImageRaw = Annotated[bytes, _event_image_raw()]
ALLOW_UPLOAD = SUPERUSER | _allow_upload

__all__ = ["ALLOW_UPLOAD", "EventImage", "EventImageRaw"]
