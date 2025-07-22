import datetime as dt
from copy import deepcopy
from typing import override
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

from src.plugins.cache import get_cache
from src.plugins.upload_cos import upload_cos

from ..adapter import converts
from ..utils import guess_url_type
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

UTC8 = dt.timezone(dt.timedelta(hours=8))
attachment_cache = get_cache[str,str](namespace="group_pipe:discord:attachment")


class MessageConverter(
    BaseMessageConverter[MessageSegment, Bot, Message],
    adapter=Adapter.get_name(),
):
    @override
    @classmethod
    async def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        message = deepcopy(event.original_message)
        attachments = {a.filename: a.url for a in event.attachments}
        for seg in message:
            if isinstance(seg, AttachmentSegment):
                attachment = seg.data["attachment"]
                if url := attachments.get(attachment.filename):
                    await attachment_cache.set(attachment.filename, url)

        return message

    @converts(
        MentionRoleSegment,
        MentionUserSegment,
        MentionChannelSegment,
        MentionEveryoneSegment,
    )
    async def mention(self, segment: MessageSegment) -> u.Segment:
        return u.Text(str(segment))

    @converts(AttachmentSegment)
    async def attachment(self, segment: AttachmentSegment) -> u.Segment:
        attachment = segment.data["attachment"]
        if url := await attachment_cache.get(attachment.filename):
            info = await guess_url_type(url)
            mime = info and info.mime

            try:
                url = await upload_cos(url, self.get_cos_key(attachment.filename))
            except Exception as err:
                self.logger.opt(exception=err).debug("上传文件失败，使用原始链接")

            return u.Image(url=url, mimetype=mime)
        return u.Text(f"[image:{attachment.filename}]")

    @converts(ReferenceSegment)
    async def reference(self, segment: ReferenceSegment) -> u.Segment | None:
        msg_id = segment.data["reference"].message_id
        return await self.convert_reply(msg_id) if msg_id is not UNSET else None

    @converts(TimestampSegment)
    async def timestamp(self, segment: TimestampSegment) -> u.Segment:
        t = dt.datetime.fromtimestamp(segment.data["timestamp"], dt.UTC)
        return u.Text(f"[time:{t.astimezone(UTC8):%Y-%m-%d %H:%M:%S}]")


class MessageSender(
    BaseMessageSender[Bot, MessageGet],
    adapter=Adapter.get_name(),
):
    @override
    @staticmethod
    def extract_msg_id(data: MessageGet) -> str:
        return str(data.id)
