from typing import Annotated

from nonebot.adapters import Message
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot_plugin_alconna.uniseg import Image, Reply, UniMessage, UniMsg


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


EventImage = Annotated[Image, _EventImage()]
