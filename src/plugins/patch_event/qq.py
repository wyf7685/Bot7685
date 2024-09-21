from typing import Any, override

from nonebot.adapters.qq.event import (
    C2CMessageCreateEvent,
    Event,
    EventType,
    GroupAtMessageCreateEvent,
    ReadyEvent,
)
from nonebot.adapters.qq.message import Message
from nonebot.utils import escape_tag

from .patcher import Patcher


def highlight_event_type(type_: EventType) -> str:
    return f"<lg>EventType</lg>.<b><e>{type_.value}</e></b>"


def color_repr(value: Any, /, *color: str) -> str:
    text = escape_tag(repr(value))
    for c in reversed(color):
        text = f"<{c}>{text}</{c}>"
    return text


def highlight_list(data: list[Any]) -> str:
    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(highlight_dict(item))
        elif isinstance(item, list):
            result.append(highlight_list(item))
        else:
            result.append(escape_tag(repr(item)))
    return "[" + ", ".join(result) + "]"


def highlight_dict(data: dict[str, Any]) -> str:
    result = []
    for key, value in data.items():
        if isinstance(value, dict):
            text = highlight_dict(value)
        elif isinstance(value, list):
            text = highlight_list(value)
        else:
            text = escape_tag(repr(value))
        result.append(f"{color_repr(key, 'c')}: {text}")
    return "{" + ", ".join(result) + "}"


def highlight_message(message: Message) -> str:
    return (
        "["
        + ", ".join(
            f"<g>{escape_tag(seg.__class__.__name__)}</g>"
            f"(type={color_repr(seg.type, 'y')}, "
            f"data={highlight_dict(seg.data)})"
            for seg in message
        )
        + "]"
    )


@Patcher
class PatchEvent(Event):
    @override
    def get_log_string(self) -> str:
        return f"[{highlight_event_type(self.__type__)}] {self.get_event_description()}"


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
