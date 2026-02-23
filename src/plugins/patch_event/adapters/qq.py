from typing import override

from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    Event,
    GroupAtMessageCreateEvent,
    ReadyEvent,
)
from nonebot.adapters.qq.message import Message, MessageSegment
from nonebot.utils import escape_tag

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight[MessageSegment, Message, Event]):
    @classmethod
    @override
    def event_type(cls, event: Event, /) -> str:
        return f"{cls.style.lg('EventType')}.{cls.style.b_e(event.__type__.value)}"


@patcher
def patch_event(self: Event) -> str:
    return f"[{H.event_type(self)}]: {H.apply(self)}"


@patcher
def patch_c2c_message_create_event(self: C2CMessageCreateEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(escape_tag(self.id))} "
        f"from {H.id(self.author.id)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_group_at_message_create_event(self: GroupAtMessageCreateEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(escape_tag(self.id))} "
        f"from {H.id(self.author.member_openid)}"
        f"@[Group:{H.id(self.group_openid)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_ready_event(self: ReadyEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Bot {H.name(self.user.id, self.user.username)} ready: "
        f"session={H.repr(self.session_id, 'b', 'e')}, "
        f"shard={H.repr(self.shard, 'b', 'e')}"
    )
