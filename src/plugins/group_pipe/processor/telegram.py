from collections.abc import AsyncGenerator
from typing import override

from nonebot.adapters.telegram import Bot, MessageSegment
from nonebot_plugin_alconna.uniseg import Image, Segment, Text

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot]):
    @override
    @classmethod
    async def process_segment(
        cls, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "mention":
                yield Text(segment.data["text"])
            case "sticker":
                file_id = segment.data["file"]
                bot = cls.get_bot()
                file = await bot.get_file(file_id)
                url = f"https://api.telegram.org/file/bot{bot.bot_config.token}/{file.file_path}"
                if raw := await download_file(url):
                    yield Image(raw=raw)
            case _:
                async for seg in super().process_segment(segment):
                    yield seg
