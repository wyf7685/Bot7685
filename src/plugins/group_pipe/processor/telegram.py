from collections.abc import AsyncIterable
from copy import deepcopy
from io import BytesIO
from typing import override

from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.telegram import Bot, Message, MessageSegment
from nonebot.adapters.telegram.event import MessageEvent
from nonebot.adapters.telegram.message import Reply as TgReply
from nonebot.adapters.telegram.model import Message as MessageModel
from nonebot_plugin_alconna.uniseg import (
    File,
    Image,
    Keyboard,
    Segment,
    Target,
    Text,
    UniMessage,
)

from src.plugins.upload_cos import upload_from_url

from ..utils import download_url, guess_url_type, webm_to_gif
from ._registry import register
from .abstract import AbstractMessageProcessor
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender


class MessageConverter(BaseMessageConverter[MessageSegment, Bot, Message]):
    @override
    @classmethod
    def get_message(cls, event: BaseEvent) -> Message | None:
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

    async def get_file_info(self, file_id: str) -> tuple[str | None, str]:
        token = self.src_bot.bot_config.token
        file_path = (await self.src_bot.get_file(file_id)).file_path
        return file_path, f"https://api.telegram.org/file/bot{token}/{file_path}"

    async def convert_image(self, file_id: str) -> Segment:
        file_path, url = await self.get_file_info(file_id)
        if file_path is None:
            return Text(f"[image:{file_id}]")

        info = await guess_url_type(url)
        if info is None:
            return Text(f"[image:{file_id}]")

        if info.mime == "video/webm":
            if raw := await download_url(url):
                raw = await webm_to_gif(raw)
                return Image(raw=raw, mimetype="image/gif")
            return Text(f"[image:{info.mime}:{file_id}]")

        try:
            url = await upload_from_url(url, self.get_cos_key(file_path))
        except Exception as err:
            self.logger.opt(exception=err).debug("上传文件失败")

        return Image(url=url, mimetype=info.mime)

    async def convert_file(self, file_id: str) -> Segment:
        file_path, url = await self.get_file_info(file_id)
        if file_path is None:
            return Text(f"[file:{file_id}]")

        info = await guess_url_type(url)
        if info is None:
            return Text(f"[file:{file_id}]")

        try:
            url = await upload_from_url(url, self.get_cos_key(file_path))
        except Exception as err:
            self.logger.opt(exception=err).debug("上传文件失败")
            return Text(f"[file:{info.mime}:{file_id}]")

        return File(
            id=file_id,
            url=url,
            mimetype=info.mime,
            name=file_path.rpartition("/")[-1],
        )

    @override
    async def convert_segment(self, segment: MessageSegment) -> AsyncIterable[Segment]:
        match segment.type:
            case "mention":
                yield Text(segment.data["text"])
            case "sticker" | "photo":
                yield await self.convert_image(segment.data["file"])
            case "document" | "video":
                yield await self.convert_file(segment.data["file"])
            case "reply":
                yield await self.convert_reply(segment.data["message_id"])
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg


class MessageSender(BaseMessageSender[Bot, MessageModel]):
    @override
    @staticmethod
    def extract_msg_id(data: MessageModel) -> str:
        return str(data.message_id) if data else ""

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: Bot,
        target: Target,
        msg: UniMessage,
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
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

        await super().send(dst_bot, target, msg, src_type, src_id)

        async with cls._send_lock(dst_bot):
            for file in gif_files:
                res = await dst_bot.send_animation(target.id, file)
                await cls._set_dst_id(src_type, src_id, dst_bot, res)


@register("Telegram")
class MessageProcessor(
    MessageConverter,
    MessageSender,
    AbstractMessageProcessor[MessageSegment, Bot, Message],
): ...
