import contextlib
from typing import TYPE_CHECKING, override

from nonebot.compat import model_dump
from nonebot.utils import escape_tag

from ..patcher import Patcher
from ..utils import color_repr, highlight_object

if TYPE_CHECKING:
    from nonebot.adapters.qq.event import EventType
    from nonebot.adapters.qq.message import Message


def highlight_event_type(type_: "EventType") -> str:
    return f"<lg>EventType</lg>.<b><e>{type_.value}</e></b>"


def highlight_message(message: "Message") -> str:
    return (
        "["
        + ", ".join(
            f"<g>{escape_tag(seg.__class__.__name__)}</g>"
            f"(type={color_repr(seg.type, 'y')}, "
            f"data={highlight_object(seg.data)})"
            for seg in message
        )
        + "]"
    )


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
            return (
                f"[{highlight_event_type(self.__type__)}] "
                f"{highlight_object(model_dump(self))}"
            )

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
