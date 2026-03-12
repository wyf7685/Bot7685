import contextlib
import datetime
import functools
from collections.abc import Iterable, Iterator
from contextvars import ContextVar
from enum import Enum
from types import EllipsisType
from typing import Any, ClassVar, Protocol

from bot7685_ext import LRU
from nonebot.adapters import Event, Message, MessageSegment
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


class _StyleCall(Protocol):
    def __call__(self, obj: object, /, *, escape: bool = False) -> str: ...


class _Style:
    def __getattr__(self, tag: str) -> _StyleCall:
        tags = tag.split("_")
        prefix = "".join(f"<{tag}>" for tag in reversed(tags))
        suffix = "</>" * len(tags)
        lru: LRU[str, str] = LRU(64)

        def fn(obj: object, /, *, escape: bool = False) -> str:
            text = escape_tag(str(obj)) if escape else str(obj)
            if text not in lru:
                lru[text] = f"{prefix}{text}{suffix}"
            return lru[text]

        setattr(self, tag, fn)
        return fn


style = _Style()
_struct_indent: ContextVar[int | None] = ContextVar(
    "bot7685_highlight_struct_indent", default=None
)


@contextlib.contextmanager
def use_struct_indent(indent: int | None = None) -> Iterator[None]:
    token = _struct_indent.set(indent)
    try:
        yield
    finally:
        _struct_indent.reset(token)


class Highlight[TMS: MessageSegment, TM: Message = Message[TMS], TE: Event = Event]:
    style: ClassVar[_Style] = style
    exclude_value: ClassVar[tuple[object, ...]] = ()
    _struct_indent: ClassVar[ContextVar[int | None]]
    _struct_depth: ClassVar[ContextVar[int]]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        cls._struct_indent = ContextVar("highlight_struct_indent", default=None)
        cls._struct_depth = ContextVar("highlight_struct_depth", default=0)

    @classmethod
    @contextlib.contextmanager
    def _use_struct_indent(cls, indent: int | None) -> Iterator[None]:
        token = cls._struct_indent.set(indent)
        try:
            yield
        finally:
            cls._struct_indent.reset(token)

    @classmethod
    @contextlib.contextmanager
    def _push_struct_depth(cls) -> Iterator[None]:
        token = cls._struct_depth.set(cls._struct_depth.get() + 1)
        try:
            yield
        finally:
            cls._struct_depth.reset(token)

    @classmethod
    def repr(cls, data: object, /, *color: str) -> str:
        text = escape_tag(repr(data))
        if color:
            prefix = "".join(f"<{tag}>" for tag in reversed(color))
            suffix = "</>" * len(color)
            text = f"{prefix}{text}{suffix}"
        return text

    @functools.singledispatchmethod
    @classmethod
    def _handle(cls, data: Any) -> str:
        return cls.repr(data)

    register = _handle.register  # pyright:ignore[reportUnannotatedClassAttribute]

    @classmethod
    def apply(cls, data: object, /, indent: int | None | EllipsisType = ...) -> str:
        if indent is ...:
            return cls._handle(data)
        with cls._use_struct_indent(indent):
            return cls._handle(data)

    @classmethod
    @functools.cache
    def enum(cls, data: Enum) -> str:
        return (
            f"<{style.g(type(data).__name__)}.{style.le(data.name)}: "
            f"{cls.apply(data.value)}>"
        )

    @register(bool)
    @classmethod
    @functools.cache
    def _(cls, data: bool) -> str:
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
        return text[0] + style.c(text[1:-1]) + text[-1]

    @classmethod
    def _seq(cls, seq: Iterable[str], bracket: str, /) -> str:
        st, ed = bracket

        indent = cls._struct_indent.get()
        if indent is None:
            return f"{st}{', '.join(seq)}{ed}"

        space = " " * indent * (cls._struct_depth.get() + 1)

        seq = list(seq)
        if not seq:
            return bracket

        if len(seq) <= 3:
            single_line = f"{st} {', '.join(seq)} {ed}"
            if len(space) + len(single_line) <= 120 and "\n" not in single_line:
                return single_line

        return (
            f"{st}\n"
            f"{',\n'.join(f'{space}{i}' for i in seq)}\n"
            f"{' ' * indent * cls._struct_depth.get()}{ed}"
        )

    @register(dict)
    @classmethod
    def _(cls, data: dict[str, object]) -> str:
        with cls._push_struct_depth():
            kv = (
                f"{cls.repr(key, 'le', 'i')}: {cls.apply(value)}"
                for key, value in data.items()
                if value not in cls.exclude_value
            )
            return cls._seq(kv, "{}")

    @register(list)
    @classmethod
    def _(cls, data: list[object]) -> str:
        with cls._push_struct_depth():
            return cls._seq(map(cls.apply, data), "[]")

    @register(set)
    @classmethod
    def _(cls, data: set[object]) -> str:
        with cls._push_struct_depth():
            return cls._seq(map(cls.apply, data), "{}")

    @register(tuple)
    @classmethod
    def _(cls, data: tuple[object]) -> str:
        with cls._push_struct_depth():
            return cls._seq(map(cls.apply, data), "()")

    @register(datetime.datetime)
    @classmethod
    def _(cls, data: datetime.datetime) -> str:
        attrs = [cls.apply(getattr(data, name)) for name in DATETIME_FIELDS]
        if data.tzinfo is not None:
            attrs.append(style.ly(data.tzinfo))
        return f"{style.g('datetime')}({', '.join(attrs)})"

    @register(BaseModel)
    @classmethod
    def _(cls, data: BaseModel) -> str:
        model = type(data)
        with cls._push_struct_depth():
            kv = (
                f"<i><y>{name}</y></i>={cls.apply(value)}"
                for name in model.model_fields
                if (value := getattr(data, name)) not in cls.exclude_value
            )
            return f"{style.lg(model.__name__)}{cls._seq(kv, '()')}"

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
            f"<g>{segment.__class__.__name__}</g>"
            f"({style.i_y('type')}={cls.apply(segment.type)},"
            f" {style.i_y('data')}={cls.apply(segment.data)})"
        )

    @classmethod
    def message(cls, message: TM) -> str:
        return f"[{', '.join(map(cls.segment, message))}]"

    @classmethod
    def id(cls, id: str | int, /) -> str:
        return style.c(id, escape=True)

    @classmethod
    def time(cls, datetime: datetime.datetime, /) -> str:
        return style.y(datetime.isoformat(sep=" ", timespec="seconds"))

    @classmethod
    def name(cls, id: str | int, name: str | None = None) -> str:
        return (
            f"{style.y(name, escape=True)}({cls.id(id)})"
            if name is not None
            else cls.id(id)
        )

    @classmethod
    def event_type(cls, event: TE, /) -> str:
        return ".".join(map(style.lg, event.get_event_name().split(".")))
