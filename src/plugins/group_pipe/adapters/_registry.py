from collections.abc import Callable
from typing import overload

from nonebot.adapters import Adapter, Bot, Message, MessageSegment

from ..adapter import MessageConverter as AbstractMessageConverter
from ..adapter import MessageSender as AbstractMessageSender

CONVERTERS: dict[str | None, type[AbstractMessageConverter]] = {}
SENDERS: dict[str | None, type[AbstractMessageSender]] = {}


def converter[T: type[AbstractMessageConverter]](
    type_: type[Adapter] | None,
) -> Callable[[T], T]:
    key = type_.get_name() if type_ is not None else None

    def decorator(cls: T) -> T:
        CONVERTERS[key] = cls
        return cls

    return decorator


def sender[T: type[AbstractMessageSender]](
    type_: type[Adapter] | None,
) -> Callable[[T], T]:
    key = type_.get_name() if type_ is not None else None

    def decorator(cls: T) -> T:
        SENDERS[key] = cls
        return cls

    return decorator


type _M = Message[MessageSegment[_M]]
type MessageConverter = AbstractMessageConverter[Bot, _M]
type MessageSender = AbstractMessageSender[Bot]


@overload
def get_converter() -> type[MessageConverter]: ...
@overload
def get_converter(adapter: str | None = None, /) -> type[MessageConverter]: ...
@overload
def get_converter(bot: Bot, /) -> type[MessageConverter]: ...
@overload
def get_converter(src_bot: Bot, dst_bot: Bot) -> MessageConverter: ...


def get_converter(
    src_bot: Bot | str | None = None,
    dst_bot: Bot | None = None,
) -> type[MessageConverter] | MessageConverter:
    if dst_bot is not None:
        if not isinstance(src_bot, Bot):
            raise TypeError("src_bot must be Bot")
        return get_converter(src_bot)(src_bot, dst_bot)

    if isinstance(src_bot, Bot):
        src_bot = src_bot.type

    return CONVERTERS[src_bot] if src_bot in CONVERTERS else CONVERTERS[None]


def get_sender(dst_bot: Bot | None = None) -> type[MessageSender]:
    return (
        SENDERS[dst_bot.type]
        if dst_bot is not None and dst_bot.type in SENDERS
        else SENDERS[None]
    )
