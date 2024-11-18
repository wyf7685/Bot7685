from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import override

from nonebot.adapters import Event
from nonebot.adapters.telegram import Bot, Message, MessageSegment, model
from nonebot.adapters.telegram import event as tgevent
from nonebot.adapters.telegram.message import Reply as TgReply
from nonebot_plugin_alconna.uniseg import Image, Reply, Segment, Text

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    @override
    @staticmethod
    def get_message(event: Event) -> Message:
        assert isinstance(event, tgevent.MessageEvent)  # noqa: S101
        message = deepcopy(event.original_message)
        if event.reply_to_message:
            reply = TgReply.reply(
                message_id=event.reply_to_message.message_id,
                chat_id=event.reply_to_message.chat.id,
            )
            message.insert(0, reply)
        return message

    @override
    @staticmethod
    async def extract_msg_id(msg_ids: list[model.Message]) -> str:
        return str(msg_ids[0].message_id) if msg_ids else ""

    async def get_file_content(self, file_id: str) -> bytes:
        bot = self.get_bot()
        token = bot.bot_config.token
        file_path = (await bot.get_file(file_id)).file_path
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        return await download_file(url)

    @override
    async def process_segment(
        self, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "mention":
                yield Text(segment.data["text"])
            case "sticker" | "photo":
                if raw := await self.get_file_content(segment.data["file"]):
                    yield Image(raw=raw)
            case "reply":
                if dst_id := await self.get_dst_id(str(segment.data["message_id"])):
                    yield Reply(dst_id)
            case _:
                async for seg in super().process_segment(segment):
                    yield seg
