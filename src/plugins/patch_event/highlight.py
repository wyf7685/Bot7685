import datetime
import functools
from enum import Enum
from typing import Any, ClassVar

from nonebot.adapters import Message, MessageSegment
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


class Highlight[TMS: MessageSegment, TM: Message = Message[TMS]]:
    exclude_value: ClassVar[tuple[object, ...]] = ()

    @classmethod
    def repr(cls, data: Any, /, *color: str) -> str:
        text = escape_tag(repr(data))
        for c in reversed(color):
            text = f"<{c}>{text}</{c}>"
        return text

    @functools.singledispatchmethod
    @classmethod
    def _handle(cls, data: Any) -> str:
        return cls.repr(data)

    register = _handle.register

    @classmethod
    def apply(cls, data: Any, /) -> str:
        return cls._handle(data)

    @classmethod
    @functools.cache
    def enum(cls, data: Enum) -> str:
        return (
            f"<<g>{type(data).__name__}</g>.<le>{data.name}</le>: "
            f"{cls.apply(data.value)}>"
        )

    @register(bool)
    @classmethod
    @functools.cache
    def _(cls, data: bool) -> str:  # noqa: FBT001
        return cls.repr(data, "lg")

    @register(int)
    @classmethod
    def _(cls, data: int) -> str:
        if isinstance(data, Enum):
            return cls.enum(data)
        return cls.repr(data, "lc", "i")

    @register(float)
    @classmethod
    def _(cls, data: float) -> str:
        return cls.repr(data, "lc", "i")

    @register(str)
    @classmethod
    def _(cls, data: str) -> str:
        if isinstance(data, Enum):
            return cls.enum(data)
        text = escape_tag(repr(data))
        return f"{text[0]}<c>{text[1:-1]}</c>{text[-1]}"

    @register(dict)
    @classmethod
    def _(cls, data: dict[str, Any]) -> str:
        kv = [
            f"{cls.repr(key, 'le', 'i')}: {cls.apply(value)}"
            for key, value in data.items()
            if value not in cls.exclude_value
        ]
        return f"{{{', '.join(kv)}}}"

    @register(list)
    @classmethod
    def _(cls, data: list[Any]) -> str:
        return f"[{', '.join(cls.apply(item) for item in data)}]"

    @register(set)
    @classmethod
    def _(cls, data: set[Any]) -> str:
        return f"{{{', '.join(cls.apply(item) for item in data)}}}"

    @register(tuple)
    @classmethod
    def _(cls, data: tuple[Any]) -> str:
        return f"({', '.join(cls.apply(item) for item in data)})"

    @register(datetime.datetime)
    @classmethod
    def _(cls, data: datetime.datetime) -> str:
        attrs = [cls.apply(getattr(data, name)) for name in DATETIME_FIELDS]
        if data.tzinfo is not None:
            attrs.append(f"<lm>{data.tzinfo}</lm>")
        return f"<g>datetime</g>({', '.join(attrs)})"

    @register(BaseModel)
    @classmethod
    def _(cls, data: BaseModel) -> str:
        kv = [
            f"<i><y>{name}</y></i>={cls.apply(value)}"
            for name in data.model_fields
            if (value := getattr(data, name)) not in cls.exclude_value
        ]
        return f"<lm>{type(data).__name__}</lm>({', '.join(kv)})"

    @classmethod
    def segment(cls, segment: TMS) -> str:
        return (
            f"<g>{escape_tag(segment.__class__.__name__)}</g>"
            f"(<i><y>type</y></i>={cls.apply(segment.type)},"
            f" <i><y>data</y></i>={cls.apply(segment.data)})"
        )

    @classmethod
    def message(cls, message: TM) -> str:
        return f"[{', '.join(map(cls.segment, message))}]"

    @register(MessageSegment)
    @classmethod
    def _(cls, data: TMS) -> str:
        return cls.segment(data)

    @register(Message)
    @classmethod
    def _(cls, data: TM) -> str:
        return cls.message(data)

    del _
