from typing import override

from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    Event,
    EventType,
    GroupAtMessageCreateEvent,
    ReadyEvent,
)
from nonebot.utils import escape_tag

from ..highlight import Highlight as BaseHighlight
from ..patcher import Patcher


class Highlight(BaseHighlight):
    @BaseHighlight.register(EventType)
    @classmethod
    def _(cls, data: EventType) -> str:
        return f"<lg>EventType</lg>.<b><e>{data.value}</e></b>"

@Patcher
class PatchEvent(Event):
    @override
    def get_log_string(self) -> str:
        return f"[{Highlight.apply(self.__type__)}] {Highlight.apply(self)}"

@Patcher
class PatchC2CMessageCreateEvent(C2CMessageCreateEvent):
    @override
    def get_log_string(self) -> str:
        return (
            f"[{Highlight.apply(self.__type__)}] "
            f"Message <c>{escape_tag(self.id)}</c> from "
            f"<c>{self.author.id}</c>: "
            f"{Highlight.apply(self.get_message())}"
        )

@Patcher
class PatchGroupAtMessageCreateEvent(GroupAtMessageCreateEvent):
    @override
    def get_log_string(self) -> str:
        return (
            f"[{Highlight.apply(self.__type__)}] "
            f"Message <c>{escape_tag(self.id)}</c> from "
            f"<c>{self.author.member_openid}</c>"
            f"@[Group:<c>{self.group_openid}</c>]: "
            f"{Highlight.apply(self.get_message())}"
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
            f"[{Highlight.apply(self.__type__)}] "
            f"Bot {name} ready: "
            f"session={Highlight.repr(self.session_id,'b','e')}, "
            f"shard={Highlight.repr(self.shard,'b','e')}"
        )
