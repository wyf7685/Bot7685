import datetime as dt
import re
from copy import deepcopy
from typing import TYPE_CHECKING, assert_never, override

import humanize
from nonebot.adapters.discord import Adapter, Bot, MessageEvent
from nonebot.adapters.discord.api.model import UNSET, MessageGet
from nonebot.adapters.discord.api.types import TimeStampStyle
from nonebot.adapters.discord.message import (
    AttachmentSegment,
    MentionChannelSegment,
    MentionEveryoneSegment,
    MentionRoleSegment,
    MentionUserSegment,
    Message,
    MessageSegment,
    ReferenceSegment,
    TextSegment,
    TimestampSegment,
)
from nonebot_plugin_alconna import uniseg as u

from src.plugins.cache import get_cache
from src.plugins.upload_cos import upload_cos

from ..adapter import converts
from ..utils import guess_url_type
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

if TYPE_CHECKING:
    from nonebot.adapters import Event as BaseEvent

UTC8 = dt.timezone(dt.timedelta(hours=8))
LINK_PATTERN = re.compile(r"\[(?P<name>.+?)\]\(<(?P<url>.+?)>\)")
attachment_cache = get_cache[str, str](namespace="group_pipe:discord:attachment")


def _weekday(d: int) -> str:
    return ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][d]


def humanize_time(time: dt.datetime, style: TimeStampStyle | None) -> str:
    match style:
        case None:
            return time.strftime("%Y-%m-%d %H:%M:%S")
        case TimeStampStyle.ShortTime:
            return time.strftime("%H:%M")
        case TimeStampStyle.LongTime:
            return time.strftime("%H:%M:%S")
        case TimeStampStyle.ShortDate:
            return time.strftime("%Y-%m-%d")
        case TimeStampStyle.LongDate:
            return time.strftime("%Y年%m月%d日")
        case TimeStampStyle.ShortDateTime:
            return time.strftime("%Y年%m月%d日 %H:%M")
        case TimeStampStyle.LongDateTime:
            return time.strftime(f"%Y年%m月%d日{_weekday(time.weekday())} %H:%M")
        case TimeStampStyle.RelativeTime:
            return humanize.naturaltime(dt.datetime.now(tz=UTC8) - time)
        case x:
            assert_never(x)


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

    @converts(TextSegment)
    async def text(self, segment: TextSegment) -> list[u.Segment]:
        text = segment.data["text"]
        result: list[u.Segment] = []
        last_ed = 0

        for match in LINK_PATTERN.finditer(text):
            name, _ = match.groups()
            st, ed = match.span()
            if st > last_ed:
                result.append(u.Text(text[last_ed:st]))
            result.append(u.Text(name).link())
            last_ed = ed
        if last_ed < len(text):
            result.append(u.Text(text[last_ed:]))

        return result

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
            media_kwds = {
                "url": url,
                "id": attachment.filename,
                "name": attachment.filename,
                "mimetype": mime,
            }
            if mime and mime.startswith("image/"):
                return u.Image(**media_kwds)
            if mime and mime.startswith("video/"):
                return u.Video(**media_kwds)
            if mime and mime.startswith("audio/"):
                return u.Audio(**media_kwds)
            return u.File(**media_kwds)
        return u.Text(f"[image:{attachment.filename}]")

    @converts(ReferenceSegment)
    async def reference(self, segment: ReferenceSegment) -> u.Segment | None:
        msg_id = segment.data["reference"].message_id
        return await self.convert_reply(msg_id) if msg_id is not UNSET else None

    @converts(TimestampSegment)
    async def timestamp(self, segment: TimestampSegment) -> u.Segment:
        timestamp = segment.data["timestamp"]
        time = dt.datetime.fromtimestamp(timestamp, dt.UTC).astimezone(UTC8)
        return u.Text(humanize_time(time, segment.data["style"]))


class MessageSender(
    BaseMessageSender[Bot, MessageGet],
    adapter=Adapter.get_name(),
):
    @override
    @staticmethod
    def extract_msg_id(data: MessageGet) -> str:
        return str(data.id)
