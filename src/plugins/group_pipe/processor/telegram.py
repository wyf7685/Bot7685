from collections.abc import AsyncGenerator
from copy import deepcopy
from io import BytesIO
from typing import TYPE_CHECKING, override

import fleep
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.telegram import Bot, Message, MessageSegment, model
from nonebot.adapters.telegram.event import MessageEvent
from nonebot.adapters.telegram.message import Reply as TgReply
from nonebot_plugin_alconna.uniseg import (
    Image,
    Keyboard,
    Receipt,
    Segment,
    Target,
    Text,
    UniMessage,
    get_exporter,
)

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    @override
    @staticmethod
    def get_message(event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

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
    def extract_msg_id(msg_ids: list[model.Message]) -> str:
        return str(msg_ids[0].message_id) if msg_ids else ""

    async def get_file_content(self, file_id: str) -> bytes:
        token = self.src_bot.bot_config.token
        file_path = (await self.src_bot.get_file(file_id)).file_path
        url = f"https://api.telegram.org/file/bot{token}/{file_path}"
        return await download_file(url)

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "mention":
                yield Text(segment.data["text"])
            case "sticker" | "photo":
                if raw := await self.get_file_content(segment.data["file"]):
                    yield Image(raw=raw, mimetype=fleep.get(raw).mime[0])
            case "reply":
                yield await self.convert_reply(segment.data["message_id"])
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg

    @override
    @classmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: Bot) -> Receipt:
        receipt: Receipt | None = None
        msg = msg.exclude(Keyboard) + msg.include(Keyboard)

        for seg in msg[Image]:
            if seg.mimetype == "image/gif" and (file := (seg.raw or seg.url)):
                msg.remove(seg)
                if isinstance(file, BytesIO):
                    file = file.read()
                if seg.name and isinstance(file, bytes):
                    file = (f"{seg.name}.gif", file)
                res = await dst_bot.send_animation(target.id, file)
                if receipt is None:
                    fn = get_exporter(dst_bot)
                    if TYPE_CHECKING:
                        assert fn is not None
                    receipt = Receipt(dst_bot, target, fn, [res])

        if not msg and receipt is not None:
            return receipt

        return await super().send(msg, target, dst_bot)
