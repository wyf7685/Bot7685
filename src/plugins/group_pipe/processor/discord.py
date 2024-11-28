from collections.abc import AsyncIterable
from copy import deepcopy
from typing import ClassVar, override
from weakref import WeakKeyDictionary

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
from nonebot_plugin_alconna import uniseg as u

from src.plugins.upload_cos import upload_from_url

from ..utils import guess_url_type
from ._registry import register
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender


class MessageConverter(BaseMessageConverter[MessageSegment, Bot, Message]):
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

    async def convert_attachment(self, attachment: AttachmentSend) -> u.Segment:
        if url := self.attachment_url.get(attachment):
            info = await guess_url_type(url)
            mime = info and info.mime

            try:
                url = await upload_from_url(url, self.get_cos_key(attachment.filename))
            except Exception as err:
                self.logger.opt(exception=err).debug("上传文件失败，使用原始链接")

            return u.Image(url=url, mimetype=mime)
        return u.Text(f"[image:{attachment.filename}]")

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncIterable[u.Segment]:
        match segment:
            case (
                MentionRoleSegment()
                | MentionUserSegment()
                | MentionChannelSegment()
                | MentionEveryoneSegment()
            ):
                yield u.Text(str(segment))
            case AttachmentSegment():
                yield await self.convert_attachment(segment.data["attachment"])
            case ReferenceSegment():
                msg_id = segment.data["reference"].message_id
                if msg_id is not UNSET:
                    yield await self.convert_reply(msg_id)
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg


class MessageSender(BaseMessageSender[Bot, MessageGet]):
    @override
    @staticmethod
    def extract_msg_id(data: MessageGet) -> str:
        return str(data.id)


@register("Discord")
class MessageProcessor(MessageSender, MessageConverter): ...
