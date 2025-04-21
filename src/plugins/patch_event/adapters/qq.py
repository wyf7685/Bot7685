from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    Event,
    EventType,
    GroupAtMessageCreateEvent,
    ReadyEvent,
)
from nonebot.utils import escape_tag

from ..highlight import Highlight as BaseHighlight
from ..patcher import patcher


class Highlight(BaseHighlight):
    @BaseHighlight.register(EventType)
    @classmethod
    def _(cls, data: EventType) -> str:
        return f"<lg>EventType</lg>.<b><e>{data.value}</e></b>"


@patcher
def patch_event(self: Event) -> str:
    return f"[{Highlight.apply(self.__type__)}] {Highlight.apply(self)}"


@patcher
def patch_c2c_message_create_event(self: C2CMessageCreateEvent) -> str:
    return (
        f"[{Highlight.apply(self.__type__)}] "
        f"Message <c>{escape_tag(self.id)}</c> from "
        f"<c>{self.author.id}</c>: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_group_at_message_create_event(self: GroupAtMessageCreateEvent) -> str:
    return (
        f"[{Highlight.apply(self.__type__)}] "
        f"Message <c>{escape_tag(self.id)}</c> from "
        f"<c>{self.author.member_openid}</c>"
        f"@[Group:<c>{self.group_openid}</c>]: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_ready_event(self: ReadyEvent) -> str:
    name = (
        f"<y>{escape_tag(username)}</y>(<c>{self.user.id}</c>)"
        if (username := self.user.username) is not None
        else f"<c>{self.user.id}</c>"
    )
    return (
        f"[{Highlight.apply(self.__type__)}] "
        f"Bot {name} ready: "
        f"session={Highlight.repr(self.session_id, 'b', 'e')}, "
        f"shard={Highlight.repr(self.shard, 'b', 'e')}"
    )
