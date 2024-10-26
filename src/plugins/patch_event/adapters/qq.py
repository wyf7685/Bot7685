import contextlib
from typing import TYPE_CHECKING, override

from nonebot.utils import escape_tag

from ..patcher import Patcher
from ..utils import color_repr, highlight_object

if TYPE_CHECKING:
    from nonebot.adapters.qq.event import EventType
    from nonebot.adapters.qq.message import Message, MessageSegment


def highlight_event_type(type_: "EventType") -> str:
    return f"<lg>EventType</lg>.<b><e>{type_.value}</e></b>"


def highlight_segment(segment: "MessageSegment") -> str:
    return (
        f"<g>{escape_tag(segment.__class__.__name__)}</g>"
        f"(type={color_repr(segment.type, 'y')}, "
        f"data={highlight_object(segment.data)})"
    )


def highlight_message(message: "Message") -> str:
    return f"[{', '.join(map(highlight_segment, message))}]"


with contextlib.suppress(ImportError):
    from nonebot.adapters.qq.event import (
        C2CMessageCreateEvent,
        Event,
        GroupAtMessageCreateEvent,
        ReadyEvent,
    )

    @Patcher
    class PatchEvent(Event):
        @override
        def get_log_string(self) -> str:
            return f"[{highlight_event_type(self.__type__)}] {highlight_object(self)}"

    @Patcher
    class PatchC2CMessageCreateEvent(C2CMessageCreateEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{highlight_event_type(self.__type__)}] "
                f"Message <c>{escape_tag(self.id)}</c> from "
                f"<c>{self.author.id}</c>: "
                f"{highlight_message(self.get_message())}"
            )

    @Patcher
    class PatchGroupAtMessageCreateEvent(GroupAtMessageCreateEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{highlight_event_type(self.__type__)}] "
                f"Message <c>{escape_tag(self.id)}</c> from "
                f"<c>{self.author.member_openid}</c>"
                f"@[Group:<c>{self.group_openid}</c>]: "
                f"{highlight_message(self.get_message())}"
            )

    @Patcher
    class PatchReadyEvent(ReadyEvent):
        @override
        def get_log_string(self) -> str:
            name = (
                f"<y>{escape_tag(username)}</y>(<c>{self.user.id}</c>)"
                if (username := self.user.username) is not None
                else f"<c>{self.user.id}</c>"
            )
            return (
                f"[{highlight_event_type(self.__type__)}] "
                f"Bot {name} ready: "
                f"session={color_repr(self.session_id,'b','e')}, "
                f"shard={color_repr(self.shard,'b','e')}"
            )
