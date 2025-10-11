import abc
import functools
from collections.abc import Awaitable, Callable
from typing import ClassVar, Self, cast, overload

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import (
    Segment,
    Target,
    UniMessage,
    get_builder,
    get_message_id,
)

type _M = Message[MessageSegment[_M]]
type ConverterPred = Callable[[MessageSegment[_M]], bool]
type ConverterCall[TC: MessageConverter, TMS: MessageSegment] = Callable[
    [TC, TMS], Awaitable[Segment | list[Segment] | None]
]
type BoundConverterCall[TMS: MessageSegment] = Callable[
    [TMS], Awaitable[Segment | list[Segment] | None]
]


CONVERTERS: dict[str | None, type[MessageConverter[Bot, _M]]] = {}
SENDERS: dict[str | None, type[MessageSender[Bot]]] = {}


class MessageConverter[TB: Bot, TM: Message](abc.ABC):
    _converter_: ClassVar[set[ConverterCall[Self, MessageSegment]]] = set()

    src_bot: TB
    dst_bot: Bot | None

    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None:
        self.src_bot = src_bot
        self.dst_bot = dst_bot

    @classmethod
    async def get_message(cls, event: Event) -> TM | None:
        return cast("TM", event.get_message())

    @classmethod
    def get_message_id(cls, event: Event, bot: TB) -> str:
        return get_message_id(event, bot)

    @abc.abstractmethod
    async def convert(self, msg: TM) -> UniMessage: ...

    def __init_subclass__(cls, adapter: str | None, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        CONVERTERS[adapter] = cls  # pyright:ignore[reportArgumentType]

        # DO NOT use `|=` which updates the original set
        # create a new set for subclass with `|`
        cls._converter_ = cls._converter_ | {
            cast("ConverterCall[Self, MessageSegment]", call)
            for name in dir(cls)
            if (call := getattr(cls, name, None)) is not None
            and callable(call)
            and hasattr(call, "__predicates__")
        }

    async def __default(self, seg: MessageSegment) -> Segment | list[Segment] | None:
        return (fn := get_builder(self.src_bot)) and fn.convert(seg)

    def _find_fn[TMS: MessageSegment](self, seg: TMS) -> BoundConverterCall[TMS]:
        for call in self._converter_:
            preds: tuple[ConverterPred, ...] = getattr(call, "__predicates__", ())
            if any(pred(seg) for pred in preds):
                return functools.partial(call, self)

        return self.__default


class MessageSender[TB: Bot](abc.ABC):
    @classmethod
    @abc.abstractmethod
    async def send(
        cls,
        dst_bot: TB,
        target: Target,
        msg: UniMessage,
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None: ...

    def __init_subclass__(cls, adapter: str | None) -> None:
        super().__init_subclass__()
        SENDERS[adapter] = cls  # pyright:ignore[reportArgumentType]


def _make_pred(t: str | type[MessageSegment]) -> ConverterPred:
    return (
        (lambda seg: seg.type == t)
        if isinstance(t, str)
        else (lambda seg: isinstance(seg, t))
    )


def converts[C: ConverterCall](*target: str | type[MessageSegment]) -> Callable[[C], C]:
    def decorator(call: C) -> C:
        preds = tuple(_make_pred(t) for t in target)
        call.__predicates__ = preds  # pyright:ignore[reportFunctionMemberAccess]
        return call

    return decorator


@overload
def get_converter() -> type[MessageConverter[Bot, _M]]: ...
@overload
def get_converter(adapter: str | None = None, /) -> type[MessageConverter[Bot, _M]]: ...
@overload
def get_converter(bot: Bot, /) -> type[MessageConverter[Bot, _M]]: ...
@overload
def get_converter(src_bot: Bot, dst_bot: Bot) -> MessageConverter[Bot, _M]: ...


def get_converter(
    src_bot: Bot | str | None = None,
    dst_bot: Bot | None = None,
) -> type[MessageConverter[Bot, _M]] | MessageConverter[Bot, _M]:
    if dst_bot is not None:
        if not isinstance(src_bot, Bot):
            raise TypeError("src_bot must be Bot")
        return get_converter(src_bot)(src_bot, dst_bot)

    if isinstance(src_bot, Bot):
        src_bot = src_bot.type

    return CONVERTERS[src_bot] if src_bot in CONVERTERS else CONVERTERS[None]


def get_sender(dst_bot: Bot | None = None) -> type[MessageSender[Bot]]:
    return (
        SENDERS[dst_bot.type]
        if dst_bot is not None and dst_bot.type in SENDERS
        else SENDERS[None]
    )
