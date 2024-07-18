from typing import Annotated

from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch
from nonebot.permission import SUPERUSER
from .database import user_has_perm


def _EventImage():

    async def event_image(msg: UniMsg) -> Image:
        if msg.has(Image):
            return msg[Image, 0]
        elif msg.has(Reply):
            reply_msg = msg[Reply, 0].msg
            if isinstance(reply_msg, Message):
                return await event_image(await UniMessage.generate(message=reply_msg))
        Matcher.skip()

    return Depends(event_image)


def _EventImageRaw():

    async def event_image_raw(
        event: Event,
        bot: Bot,
        state: T_State,
        image: EventImage,
    ) -> bytes:
        if isinstance(raw := await image_fetch(event, bot, state, image), bytes):
            return raw
        Matcher.skip()

    return Depends(event_image_raw)


async def _allow_upload(event: Event):
    return await user_has_perm(event.get_user_id())


EventImage = Annotated[Image, _EventImage()]
EventImageRaw = Annotated[bytes, _EventImageRaw()]
ALLOW_UPLOAD = SUPERUSER | _allow_upload
