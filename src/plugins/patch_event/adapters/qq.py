from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    Event,
    EventType,
    GroupAtMessageCreateEvent,
    ReadyEvent,
)
from nonebot.utils import escape_tag

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight):
    @Highlight.register(EventType)
    @classmethod
    def _(cls, data: EventType) -> str:
        return f"<lg>EventType</lg>.<b><e>{data.value}</e></b>"


@patcher
def patch_event(self: Event) -> str:
    return f"[{H.apply(self.__type__)}] {H.apply(self)}"


@patcher
def patch_c2c_message_create_event(self: C2CMessageCreateEvent) -> str:
    return (
        f"[{H.apply(self.__type__)}] "
        f"Message {H.id(escape_tag(self.id))} "
        f"from {H.id(self.author.id)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_group_at_message_create_event(self: GroupAtMessageCreateEvent) -> str:
    return (
        f"[{H.apply(self.__type__)}] "
        f"Message {H.id(escape_tag(self.id))} "
        f"from {H.id(self.author.member_openid)}"
        f"@[Group:{H.id(self.group_openid)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_ready_event(self: ReadyEvent) -> str:
    name = (
        f"<y>{escape_tag(username)}</y>({H.id(self.user.id)})"
        if (username := self.user.username) is not None
        else H.id(self.user.id)
    )
    return (
        f"[{H.apply(self.__type__)}] "
        f"Bot {name} ready: "
        f"session={H.repr(self.session_id, 'b', 'e')}, "
        f"shard={H.repr(self.shard, 'b', 'e')}"
    )
