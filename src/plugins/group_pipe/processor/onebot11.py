from collections.abc import AsyncGenerator
from typing import override

from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot_plugin_alconna.uniseg import Image, Segment, Text

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


class MessageProcessor(BaseMessageProcessor[MessageSegment]):
    @override
    @classmethod
    async def process_segment(
        cls, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "at":
                yield Text(f"[at:{segment.data['qq']}]")
            case "image":
                if url := segment.data.get("url"):
                    yield (
                        Image(raw=raw)
                        if (raw := await download_file(url))
                        else Image(url=url)
                    )
            case "reply":
                # todo
                pass
            case "json":
                yield Text(f"[json消息:{segment.data['data']}]")
            case _:
                async for seg in super().process_segment(segment):
                    yield seg
