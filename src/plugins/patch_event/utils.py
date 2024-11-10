import datetime
import functools
import inspect
from collections.abc import Callable
from enum import Enum
from typing import Any, get_origin

from nonebot.adapters import Message, MessageSegment
from nonebot.compat import model_dump
from nonebot.utils import escape_tag
from pydantic import BaseModel


def color_repr(value: Any, /, *color: str) -> str:
    text = escape_tag(repr(value))
    for c in reversed(color):
        text = f"<{c}>{text}</{c}>"
    return text


_registry: dict[type, Callable[[Any], str]] = {}


def _register[T](call: Callable[[T], str]) -> Callable[[T], str]:
    type_ = inspect.signature(call).parameters["data"].annotation
    if origin := get_origin(type_):
        type_ = origin
    _registry[type_] = call
    return call


@_register
@functools.cache
def _(data: Enum) -> str:
    return (
        f"<<m>{type(data).__name__}</m>.<m>{data.name}</m>: "
        f"{highlight_object(data.value)}>"
    )


@_register
@functools.cache
def _(data: bool) -> str:  # noqa: FBT001
    return color_repr(data, "g")


@_register
def _(data: int) -> str:
    return color_repr(data, "c")


@_register
def _(data: float) -> str:
    return color_repr(data, "c")


@_register
def _(data: str) -> str:
    text = escape_tag(repr(data))
    return f"{text[0]}<c>{text[1:-1]}</c>{text[-1]}"


@_register
def _(data: dict[str, Any]) -> str:
    return (
        "{"
        + ", ".join(
            f"{color_repr(key, 'e')}: {highlight_object(value)}"
            for key, value in data.items()
        )
        + "}"
    )


@_register
def _(data: list[Any]) -> str:
    return "[" + ", ".join(highlight_object(item) for item in data) + "]"


@_register
def _(data: set[Any]) -> str:
    return "{" + ", ".join(highlight_object(item) for item in data) + "}"


@_register
def _(data: tuple[Any]) -> str:
    return "(" + ", ".join(highlight_object(item) for item in data) + ")"


@_register
def _(data: datetime.datetime) -> str:
    attrs = [
        highlight_object(getattr(data, name))
        for name in ["year", "month", "day", "hour", "minute", "second", "microsecond"]
    ]
    if data.tzinfo is not None:
        attrs.append(f"<m>{data.tzinfo}</m>")
    return "<m>datetime</m>.<m>datetime</m>(" + ", ".join(attrs) + ")"


@_register
def _(data: BaseModel) -> str:
    return (
        f"<m>{type(data).__name__}</m>("
        + ", ".join(
            f"<y>{k}</y>={highlight_object(v)}" for k, v in model_dump(data).items()
        )
        + ")"
    )


def highlight_object(value: Any) -> str:
    for type_, call in _registry.items():
        if isinstance(value, type_):
            return call(value)
    else:
        return color_repr(value)


def highlight_segment(segment: MessageSegment) -> str:
    return (
        f"<m>{escape_tag(segment.__class__.__name__)}</m>"
        f"(<y>type</y>={highlight_object(segment.type)}, "
        f"<y>data</y>={highlight_object(segment.data)})"
    )


def highlight_message[MS: MessageSegment](
    message: Message[MS],
    highlight_segment: Callable[[MS], str] = highlight_segment,
) -> str:
    return f"[{', '.join(map(highlight_segment, message))}]"
