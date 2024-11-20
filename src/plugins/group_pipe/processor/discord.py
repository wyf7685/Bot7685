from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import override

from nonebot.adapters import Event
from nonebot.adapters.discord import Bot, MessageEvent
from nonebot.adapters.discord.api.model import UNSET, MessageGet
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

from .common import MessageProcessor as BaseMessageProcessor


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    @override
    @staticmethod
    def get_message(event: Event) -> Message:
        assert isinstance(event, MessageEvent)  # noqa: S101
        message = deepcopy(event.original_message)
        attachments = {a.filename: a.url for a in event.attachments}
        for seg in message:
            if isinstance(seg, AttachmentSegment):
                attachment = seg.data["attachment"]
                if attachment.filename in attachments:
                    attachment.description = attachments[attachment.filename]
        return message

    @override
    @staticmethod
    async def extract_msg_id(msg_ids: list[MessageGet]) -> str:
        return str(msg_ids[0].id)

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment:
            case (
                MentionRoleSegment()
                | MentionUserSegment()
                | MentionChannelSegment()
                | MentionEveryoneSegment()
            ):
                yield Text(str(segment))
            case AttachmentSegment():
                url = segment.data["attachment"].description
                yield Image(url=url)
            case ReferenceSegment():
                msg_id = segment.data["reference"].message_id
                if msg_id is not UNSET:
                    yield await self.convert_reply(msg_id)
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg
