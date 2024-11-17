from typing import override

import httpx
from nonebot_plugin_alconna.uniseg import At, Image, Reply, Text, UniMessage
from nonebot_plugin_alconna.uniseg.utils import fleep

from .common import MessageProcessor as BaseMessageProcessor


async def create_image_seg(url: str) -> Image:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code != 200:
            return Image(id=str(hash(url)), url=url)
        data = resp.read()
    ext = fleep.get(data).extensions[0]
    name = f"{hash(url)}.{ext}"
    return Image(id=name, raw=data, name=name)


class MessageProcessor(BaseMessageProcessor):
    @override
    @classmethod
    async def process(cls, msg: UniMessage) -> UniMessage:
        result = UniMessage()
        for seg in msg:
            if isinstance(seg, Image) and seg.url is not None:
                seg = await create_image_seg(seg.url)
            elif isinstance(seg, At):
                seg = Text(f"[at:{seg.target}]")
            elif isinstance(seg, Reply):
                continue
            result.append(seg)
        return result
