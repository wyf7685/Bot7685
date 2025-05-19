import datetime
import functools
from collections.abc import Iterable
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
    def repr(cls, data: object, /, *color: str) -> str:
        text = escape_tag(repr(data))
        for c in reversed(color):
            text = f"<{c}>{text}</{c}>"
        return text

    @functools.singledispatchmethod
    @classmethod
    def _handle(cls, data: Any) -> str:
        return cls.repr(data)

    register = _handle.register  # pyright:ignore[reportUnannotatedClassAttribute]

    @classmethod
    def apply(cls, data: object, /) -> str:
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
        return cls.enum(data) if isinstance(data, Enum) else cls.repr(data, "lc", "i")

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

    @staticmethod
    def _seq(seq: Iterable[str], bracket: str, /) -> str:
        st, ed = bracket
        return f"{st}{', '.join(seq)}{ed}"

    @register(dict)
    @classmethod
    def _(cls, data: dict[str, object]) -> str:
        kv = (
            f"{cls.repr(key, 'le', 'i')}: {cls.apply(value)}"
            for key, value in data.items()
            if value not in cls.exclude_value
        )
        return cls._seq(kv, "{}")

    @register(list)
    @classmethod
    def _(cls, data: list[object]) -> str:
        return cls._seq(map(cls.apply, data), "[]")

    @register(set)
    @classmethod
    def _(cls, data: set[object]) -> str:
        return cls._seq(map(cls.apply, data), "{}")

    @register(tuple)
    @classmethod
    def _(cls, data: tuple[object]) -> str:
        return cls._seq(map(cls.apply, data), "()")

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
        model = type(data)
        kv = (
            f"<i><y>{name}</y></i>={cls.apply(value)}"
            for name in model.model_fields
            if (value := getattr(data, name)) not in cls.exclude_value
        )
        return f"<lm>{model.__name__}</lm>({', '.join(kv)})"

    @register(MessageSegment)
    @classmethod
    def _(cls, data: TMS) -> str:
        return cls.segment(data)

    @register(Message)
    @classmethod
    def _(cls, data: TM) -> str:
        return cls.message(data)

    del _

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

    @classmethod
    def id(cls, id: str | int) -> str:
        if isinstance(id, str):
            id = escape_tag(id)
        return f"<c>{id}</c>"

    @classmethod
    def time(cls, datetime: datetime.datetime) -> str:
        return f"<y>{datetime:%Y-%m-%d %H:%M:%S}</y>"

    @classmethod
    def _name(cls, id: str | int, name: str | None = None) -> str:
        return (
            f"<y>{escape_tag(name)}</y>({cls.id(id)})"
            if name is not None
            else cls.id(id)
        )

    @classmethod
    def event_type(cls, event_type: str) -> str:
        parts = event_type.split(".")
        return ".".join(f"<lg>{part}</lg>" for part in parts)
