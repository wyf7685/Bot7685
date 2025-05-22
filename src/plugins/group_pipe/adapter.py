import abc
import functools
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import ClassVar, Self, cast, overload

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment, Target, UniMessage

type _M = Message[MessageSegment[_M]]
type ConverterPred = Callable[[MessageSegment[_M]], bool]
type ConverterCall[TC: MessageConverter, TMS: MessageSegment] = (
    Callable[[TC, TMS], AsyncGenerator[Segment]]
    | Callable[[TC, TMS], Awaitable[Segment | None]]
)
type BoundConverterCall[TMS: MessageSegment] = (
    Callable[[TMS], AsyncGenerator[Segment]]
    | Callable[[TMS], Awaitable[Segment | None]]
)

CONVERTERS: dict[str | None, type["MessageConverter[Bot, _M]"]] = {}
SENDERS: dict[str | None, type["MessageSender[Bot]"]] = {}


class MessageConverter[TB: Bot, TM: Message](abc.ABC):
    _adapter_: ClassVar[str | None]
    _converter_: ClassVar[set[ConverterCall[Self, MessageSegment]]] = set()

    src_bot: TB
    dst_bot: Bot | None

    @abc.abstractmethod
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None: ...

    @classmethod
    @abc.abstractmethod
    def get_message(cls, event: Event) -> TM | None: ...

    @classmethod
    @abc.abstractmethod
    def get_message_id(cls, event: Event, bot: TB) -> str: ...

    @abc.abstractmethod
    async def convert(self, msg: TM) -> UniMessage[Segment]: ...

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if hasattr(cls, "_adapter_"):
            CONVERTERS[cls._adapter_] = cls  # pyright:ignore[reportArgumentType]
            del cls._adapter_

        # DO NOT use `|=` which will update the original set (weird)
        # create a new set for subclass using operator `|`
        cls._converter_ = cls._converter_ | {
            cast("ConverterCall[Self, MessageSegment]", call)
            for name in dir(cls)
            if (call := getattr(cls, name, None)) is not None
            and callable(call)
            and hasattr(call, "__predicates__")
        }

    def _find_fn(
        self, seg: MessageSegment
    ) -> BoundConverterCall[MessageSegment] | None:
        for call in self._converter_:
            preds: tuple[ConverterPred, ...] = getattr(call, "__predicates__", ())
            if any(pred(seg) for pred in preds):
                return functools.partial(call, self)  # pyright:ignore[reportReturnType]
        return None


class MessageSender[TB: Bot](abc.ABC):
    _adapter_: ClassVar[str | None]

    @classmethod
    @abc.abstractmethod
    async def send(
        cls,
        dst_bot: TB,
        target: Target,
        msg: UniMessage[Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None: ...

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if hasattr(cls, "_adapter_"):
            SENDERS[cls._adapter_] = cls  # pyright:ignore[reportArgumentType]
            del cls._adapter_


def _make_pred(t: str | type[MessageSegment]) -> ConverterPred:
    return (
        (lambda seg: seg.type == t)
        if isinstance(t, str)
        else (lambda seg: isinstance(seg, t))
    )


def mark[TC: MessageConverter, TMS: MessageSegment](
    *target: str | type[TMS],
) -> Callable[[ConverterCall[TC, TMS]], ConverterCall[TC, TMS]]:
    def decorator[T: Callable](call: T) -> T:
        call.__predicates__ = tuple(_make_pred(t) for t in target)  # pyright:ignore[reportFunctionMemberAccess]
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
