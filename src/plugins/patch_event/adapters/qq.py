import contextlib
from typing import override

from nonebot.utils import escape_tag

from ..patcher import Patcher
from ..utils import Highlight as _Highlight


class Highlight(_Highlight):
    @classmethod
    def event_type(cls, type_: "EventType") -> str:
        return f"<lg>EventType</lg>.<b><e>{type_.value}</e></b>"


with contextlib.suppress(ImportError):
    from nonebot.adapters.qq.event import (
        C2CMessageCreateEvent,
        Event,
        EventType,
        GroupAtMessageCreateEvent,
        ReadyEvent,
    )

    @Patcher
    class PatchEvent(Event):
        @override
        def get_log_string(self) -> str:
            return f"[{Highlight.event_type(self.__type__)}] {Highlight.object(self)}"

    @Patcher
    class PatchC2CMessageCreateEvent(C2CMessageCreateEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{Highlight.event_type(self.__type__)}] "
                f"Message <c>{escape_tag(self.id)}</c> from "
                f"<c>{self.author.id}</c>: "
                f"{Highlight.message(self.get_message())}"
            )

    @Patcher
    class PatchGroupAtMessageCreateEvent(GroupAtMessageCreateEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{Highlight.event_type(self.__type__)}] "
                f"Message <c>{escape_tag(self.id)}</c> from "
                f"<c>{self.author.member_openid}</c>"
                f"@[Group:<c>{self.group_openid}</c>]: "
                f"{Highlight.message(self.get_message())}"
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
                f"[{Highlight.event_type(self.__type__)}] "
                f"Bot {name} ready: "
                f"session={Highlight.repr(self.session_id,'b','e')}, "
                f"shard={Highlight.repr(self.shard,'b','e')}"
            )
