from typing import Annotated

from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch

from .database import user_has_perm


def _event_image() -> Image:
    async def event_image(msg: UniMsg) -> Image:
        if msg.has(Image):
            return msg[Image, 0]
        if msg.has(Reply):
            reply_msg = msg[Reply, 0].msg
            if isinstance(reply_msg, Message):
                return await event_image(await UniMessage.generate(message=reply_msg))
        return Matcher.skip()

    return Depends(event_image)


def _event_image_raw() -> bytes:
    async def event_image_raw(
        event: Event,
        bot: Bot,
        state: T_State,
        image: EventImage,
    ) -> bytes:
        if isinstance(raw := await image_fetch(event, bot, state, image), bytes):
            return raw
        return Matcher.skip()

    return Depends(event_image_raw)


async def _allow_upload(event: Event) -> bool:
    return await user_has_perm(event.get_user_id())


EventImage = Annotated[Image, _event_image()]
EventImageRaw = Annotated[bytes, _event_image_raw()]
ALLOW_UPLOAD = SUPERUSER | _allow_upload
