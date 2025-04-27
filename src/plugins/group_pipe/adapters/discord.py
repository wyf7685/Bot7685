import datetime as dt
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import ClassVar, override
from weakref import WeakKeyDictionary

from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.discord import Adapter, Bot, MessageEvent
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
    TimestampSegment,
)
from nonebot_plugin_alconna import uniseg as u

from src.plugins.upload_cos import upload_cos

from ..adapter import mark
from ..utils import guess_url_type, make_generator
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

UTC8 = dt.timezone(dt.timedelta(hours=8))


class MessageConverter(BaseMessageConverter[MessageSegment, Bot, Message]):
    _adapter_: ClassVar[str | None] = Adapter.get_name()
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

    @mark(
        MentionRoleSegment,
        MentionUserSegment,
        MentionChannelSegment,
        MentionEveryoneSegment,
    )
    async def mention(self, segment: MessageSegment) -> AsyncGenerator[u.Segment]:
        yield u.Text(str(segment))

    @mark(AttachmentSegment)
    @make_generator
    async def attachment(self, segment: AttachmentSegment) -> u.Segment:
        attachment = segment.data["attachment"]
        if url := self.attachment_url.get(attachment):
            info = await guess_url_type(url)
            mime = info and info.mime

            try:
                url = await upload_cos(url, self.get_cos_key(attachment.filename))
            except Exception as err:
                self.logger.opt(exception=err).debug("上传文件失败，使用原始链接")

            return u.Image(url=url, mimetype=mime)
        return u.Text(f"[image:{attachment.filename}]")

    @mark(ReferenceSegment)
    @make_generator
    async def reference(self, segment: ReferenceSegment) -> u.Segment | None:
        msg_id = segment.data["reference"].message_id
        return await self.convert_reply(msg_id) if msg_id is not UNSET else None

    @mark(TimestampSegment)
    @make_generator
    async def timestamp(self, segment: TimestampSegment) -> u.Segment:
        t = dt.datetime.fromtimestamp(segment.data["timestamp"], dt.UTC)
        return u.Text(f"[time:{t.astimezone(UTC8):%Y-%m-%d %H:%M:%S}]")


class MessageSender(BaseMessageSender[Bot, MessageGet]):
    _adapter_: ClassVar[str | None] = Adapter.get_name()

    @override
    @staticmethod
    def extract_msg_id(data: MessageGet) -> str:
        return str(data.id)
