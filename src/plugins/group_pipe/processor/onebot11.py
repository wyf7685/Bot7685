from typing import override

from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage

from .common import MessageProcessor as BaseMessageProcessor


class MessageProcessor(BaseMessageProcessor):
    @override
    @classmethod
    async def process(cls, msg: UniMessage) -> UniMessage:
        result = UniMessage()
        for seg in msg:
            if isinstance(seg, Image) and seg.id is not None:
                seg = Image(url=seg.url)
            elif isinstance(seg, At):
                seg = Text(f"[at:{seg.target}]")
            elif isinstance(seg, Reply):
                continue
            result.append(seg)
        return result
