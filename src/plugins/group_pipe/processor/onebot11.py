from collections.abc import AsyncGenerator
from typing import Any, override

from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot_plugin_alconna.uniseg import Image, Reply, Segment, Text

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    @override
    @staticmethod
    def get_message(event: Event) -> Message:
        assert isinstance(event, MessageEvent)  # noqa: S101
        return event.original_message

    @override
    @staticmethod
    async def extract_msg_id(msg_ids: list[dict[str, Any]]) -> str:
        return str(msg_ids[0]["message_id"]) if msg_ids else ""

    @override
    async def convert_segment(
        self, segment: MessageSegment
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
                msg_id = str(segment.data["id"])
                if reply_id := await self.get_reply_id(msg_id):
                    yield Reply(reply_id)
            case "json":
                yield Text(f"[json消息:{segment.data['data']}]")
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg
