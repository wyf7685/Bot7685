import datetime
import functools
from enum import Enum
from typing import Any

from nonebot.adapters import Message, MessageSegment
from nonebot.compat import model_dump
from nonebot.utils import escape_tag
from pydantic import BaseModel

DATETIME_FIELDS = [
    "year",
    "month",
    "day",
    "hour",
    "minute",
    "second",
    "microsecond",
]


class Highlight[MS: MessageSegment]:
    @classmethod
    def repr(cls, data: Any, /, *color: str) -> str:
        text = escape_tag(repr(data))
        for c in reversed(color):
            text = f"<{c}>{text}</{c}>"
        return text

    @functools.singledispatchmethod
    @classmethod
    def object(cls, data: Any) -> str:
        return cls.repr(data)

    @object.register(Enum)
    @classmethod
    @functools.cache
    def _(cls, data: Enum) -> str:
        return (
            f"<<m>{type(data).__name__}</m>.<m>{data.name}</m>: "
            f"{cls.object(data.value)}>"
        )

    @object.register(bool)
    @classmethod
    @functools.cache
    def _(cls, data: bool) -> str:  # noqa: FBT001
        return cls.repr(data, "g")

    @object.register(int)
    @classmethod
    def _(cls, data: int) -> str:
        return cls.repr(data, "c")

    @object.register(float)
    @classmethod
    def _(cls, data: float) -> str:
        return cls.repr(data, "c")

    @object.register(str)
    @classmethod
    def _(cls, data: str) -> str:
        text = escape_tag(repr(data))
        return f"{text[0]}<c>{text[1:-1]}</c>{text[-1]}"

    @object.register(dict)
    @classmethod
    def _(cls, data: dict[str, Any]) -> str:
        kv = [
            f"{cls.repr(key, 'e', 'i')}: {cls.object(value)}"
            for key, value in data.items()
        ]
        return f"{{{', '.join(kv)}}}"

    @object.register(list)
    @classmethod
    def _(cls, data: list[Any]) -> str:
        return f"[{', '.join(cls.object(item) for item in data)}]"

    @object.register(set)
    @classmethod
    def _(cls, data: set[Any]) -> str:
        return f"{{{', '.join(cls.object(item) for item in data)}}}"

    @object.register(tuple)
    @classmethod
    def _(cls, data: tuple[Any]) -> str:
        return f"({', '.join(cls.object(item) for item in data)})"

    @object.register(datetime.datetime)
    @classmethod
    def _(cls, data: datetime.datetime) -> str:
        attrs = [cls.object(getattr(data, name)) for name in DATETIME_FIELDS]
        if data.tzinfo is not None:
            attrs.append(f"<m>{data.tzinfo}</m>")
        return f"<m>datetime</m>.<m>datetime</m>({', '.join(attrs)})"

    @object.register(BaseModel)
    @classmethod
    def _(cls, data: BaseModel) -> str:
        kv = [f"<i><y>{k}</y></i>={cls.object(v)}" for k, v in model_dump(data).items()]
        return f"<m>{type(data).__name__}</m>({', '.join(kv)})"

    @classmethod
    def segment(cls, segment: MS) -> str:
        return (
            f"<m>{escape_tag(segment.__class__.__name__)}</m>"
            f"(<y>type</y>={cls.object(segment.type)}, "
            f"<y>data</y>={cls.object(segment.data)})"
        )

    @classmethod
    def message(cls, message: Message[MS]) -> str:
        return f"[{', '.join(map(cls.segment, message))}]"
