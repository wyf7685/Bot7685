from collections.abc import Callable
from typing import Protocol, overload

from nonebot.adapters import Adapter, Bot, Event, Message
from nonebot_plugin_alconna.uniseg import Segment, Target, UniMessage


class MessageConverterProtocol[TB: Bot, TM: Message](Protocol):
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None: ...
    @classmethod
    def get_message(cls, event: Event) -> TM | None: ...
    @classmethod
    def get_message_id(cls, event: Event, bot: TB) -> str: ...
    async def convert(self, msg: TM) -> UniMessage[Segment]: ...


class MessageSenderProtocol[TB: Bot](Protocol):
    @classmethod
    async def send(
        cls,
        dst_bot: TB,
        target: Target,
        msg: UniMessage[Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None: ...


CONVERTERS: dict[str | None, type[MessageConverterProtocol]] = {}
SENDERS: dict[str | None, type[MessageSenderProtocol]] = {}


def converter[
    T: type[MessageConverterProtocol]
](type_: type[Adapter] | None) -> Callable[[T], T]:
    key = type_.get_name() if type_ is not None else None

    def decorator(cls: T) -> T:
        CONVERTERS[key] = cls
        return cls

    return decorator


def sender[
    T: type[MessageSenderProtocol]
](type_: type[Adapter] | None) -> Callable[[T], T]:
    key = type_.get_name() if type_ is not None else None

    def decorator(cls: T) -> T:
        SENDERS[key] = cls
        return cls

    return decorator


type MessageConverter = MessageConverterProtocol[Bot, Message]
type MessageSender = MessageSenderProtocol[Bot]


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
