from collections.abc import AsyncGenerator
from copy import deepcopy
from io import BytesIO
from typing import override

import nonebot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.telegram import Bot, Message, MessageSegment, model
from nonebot.adapters.telegram.event import MessageEvent
from nonebot.adapters.telegram.message import Reply as TgReply
from nonebot_plugin_alconna.uniseg import (
    File,
    Image,
    Keyboard,
    Segment,
    Target,
    Text,
    UniMessage,
)

from ..utils import download_url, get_file_type, guess_url_type, webm_to_gif
from .common import MessageProcessor as BaseMessageProcessor

logger = nonebot.logger.opt(colors=True)


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
    def extract_msg_id(res: model.Message) -> str:
        return str(res.message_id) if res else ""

    async def get_file_url(self, file_id: str) -> str:
        token = self.src_bot.bot_config.token
        file_path = (await self.src_bot.get_file(file_id)).file_path
        return f"https://api.telegram.org/file/bot{token}/{file_path}"

    async def get_file_content(self, file_id: str) -> bytes:
        url = await self.get_file_url(file_id)
        return await download_url(url)

    async def convert_document(self, file_id: str) -> Segment | None:
        url = await self.get_file_url(file_id)
        info = await guess_url_type(url)
        if info is None:
            return Text(f"[file:{file_id}]")

        try:
            from src.plugins.upload_cos import upload_from_url

            url = await upload_from_url(url, key=f"document/{file_id}")
        except Exception as err:
            logger.opt(exception=err).debug("上传文件失败")
            return Text(f"[file:{info.mime}:{file_id}]")
        else:
            return File(
                id=file_id,
                url=url,
                mimetype=info.mime,
                name=f"{hash(file_id)}.{info.extension}",
            )

    @override
    async def convert_segment(self, segment: MessageSegment) -> AsyncGenerator[Segment]:
        match segment.type:
            case "mention":
                yield Text(segment.data["text"])
            case "sticker" | "photo":
                if raw := await self.get_file_content(segment.data["file"]):
                    mime = get_file_type(raw).mime
                    if mime == "video/webm":
                        raw = await webm_to_gif(raw)
                        mime = "image/gif"
                    yield Image(raw=raw, mimetype=mime)
            case "document":
                if seg := await self.convert_document(segment.data["file"]):
                    yield seg
            case "reply":
                yield await self.convert_reply(segment.data["message_id"])
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg

    @override
    @classmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: Bot) -> list[str]:
        msg = msg.exclude(Keyboard) + msg.include(Keyboard)

        # alc 里没有处理 gif (animation) 的逻辑
        # 提取出来单独发送
        gif_files: list[tuple[str, bytes] | bytes | str] = []
        for seg in msg[Image]:
            if seg.mimetype == "image/gif" and (file := (seg.raw or seg.url)):
                msg.remove(seg)
                if isinstance(file, BytesIO):
                    file = file.read()
                if seg.name and isinstance(file, bytes):
                    file = (f"{seg.name}.gif", file)
                gif_files.append(file)

        msg_ids = await super().send(msg, target, dst_bot)
        for file in gif_files:
            res = await dst_bot.send_animation(target.id, file)
            msg_ids.append(cls.extract_msg_id(res))

        return msg_ids
