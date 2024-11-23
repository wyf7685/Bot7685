from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import ClassVar, override
from weakref import WeakKeyDictionary

import nonebot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot.adapters.discord.api.model import UNSET, AttachmentSend, MessageGet
from nonebot.adapters.discord.message import (
    AttachmentSegment,
    MentionChannelSegment,
    MentionEveryoneSegment,
    MentionRoleSegment,
    MentionUserSegment,
    Message,
    MessageSegment,
    ReferenceSegment,
)
from nonebot_plugin_alconna.uniseg import Image, Segment, Text

from src.plugins.upload_cos import upload_from_url

from ..utils import guess_url_type
from .common import MessageProcessor as BaseMessageProcessor

logger = nonebot.logger.opt(colors=True)


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    attachment_url: ClassVar[WeakKeyDictionary[AttachmentSend, str]] = (
        WeakKeyDictionary()
    )

    @override
    @classmethod
    def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        message = deepcopy(event.original_message)
        attachments = {a.filename: a.url for a in event.attachments}
        for seg in message:
            if isinstance(seg, AttachmentSegment):
                attachment = seg.data["attachment"]
                if url := attachments.get(attachment.filename):
                    cls.attachment_url[attachment] = url

        return message

    @override
    @staticmethod
    def extract_msg_id(res: MessageGet) -> str:
        return str(res.id)

    async def convert_attachment(self, attachment: AttachmentSend) -> Segment:
        if url := self.attachment_url.get(attachment):
            info = await guess_url_type(url)
            mime = info and info.mime

            try:
                url = await upload_from_url(url, attachment.filename)
            except Exception as err:
                logger.opt(exception=err).debug("上传文件失败，使用原始链接")

            return Image(url=url, mimetype=mime)
        return Text(f"[image:{attachment.filename}]")

    @override
    async def convert_segment(self, segment: MessageSegment) -> AsyncGenerator[Segment]:
        match segment:
            case (
                MentionRoleSegment()
                | MentionUserSegment()
                | MentionChannelSegment()
                | MentionEveryoneSegment()
            ):
                yield Text(str(segment))
            case AttachmentSegment():
                yield await self.convert_attachment(segment.data["attachment"])
            case ReferenceSegment():
                msg_id = segment.data["reference"].message_id
                if msg_id is not UNSET:
                    yield await self.convert_reply(msg_id)
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg
