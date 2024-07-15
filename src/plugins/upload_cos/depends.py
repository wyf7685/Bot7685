from typing import Annotated

from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.typing import T_State
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg, image_fetch


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


EventImage = Annotated[Image, _EventImage()]
EventImageRaw = Annotated[bytes, _EventImageRaw()]
