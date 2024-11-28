from collections.abc import Callable
from typing import cast, overload

from nonebot.adapters import Bot

from .abstract import AbstractMessageProcessor

PROCESSORS: dict[str | None, type[AbstractMessageProcessor]] = {}


def register[T](type_: str | None) -> Callable[[T], T]:
    def decorator(processor: T) -> T:
        PROCESSORS[type_] = cast(type[AbstractMessageProcessor], processor)
        return processor

    return decorator


@overload
def get_processor() -> type[AbstractMessageProcessor]: ...
@overload
def get_processor(adapter: str | None = None, /) -> type[AbstractMessageProcessor]: ...
@overload
def get_processor(bot: Bot, /) -> type[AbstractMessageProcessor]: ...
@overload
def get_processor(src_bot: Bot, dst_bot: Bot) -> AbstractMessageProcessor: ...


def get_processor(
    src_bot: Bot | str | None = None,
    dst_bot: Bot | None = None,
) -> type[AbstractMessageProcessor] | AbstractMessageProcessor:
    if dst_bot is not None:
        if not isinstance(src_bot, Bot):
            raise TypeError("src_bot must be Bot")
        return get_processor(src_bot)(src_bot, dst_bot)

    if isinstance(src_bot, Bot):
        src_bot = src_bot.type

    if src_bot in PROCESSORS:
        return PROCESSORS[src_bot]

    from .common import MessageProcessor

    return MessageProcessor
