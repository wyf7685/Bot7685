from collections.abc import Callable
from typing import Protocol, cast, overload

from nonebot.adapters import Bot, Event, Message
from nonebot_plugin_alconna.uniseg import Segment, Target, UniMessage


class MessageProcessorProtocol[TB: Bot, TM: Message](Protocol):
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None: ...
    @classmethod
    def get_message(cls, event: Event) -> TM | None: ...
    async def convert(self, msg: TM) -> UniMessage[Segment]: ...
    @classmethod
    async def send(
        cls,
        dst_bot: TB,
        target: Target,
        msg: UniMessage[Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None: ...


PROCESSORS: dict[str | None, type[MessageProcessorProtocol]] = {}


def register[T: type[MessageProcessorProtocol]](type_: str | None) -> Callable[[T], T]:
    def decorator(processor: T) -> T:
        PROCESSORS[type_] = cast(type[MessageProcessorProtocol], processor)
        return processor

    return decorator


type MessageProcessor = MessageProcessorProtocol[Bot, Message]


@overload
def get_processor() -> type[MessageProcessor]: ...
@overload
def get_processor(adapter: str | None = None, /) -> type[MessageProcessor]: ...
@overload
def get_processor(bot: Bot, /) -> type[MessageProcessor]: ...
@overload
def get_processor(src_bot: Bot, dst_bot: Bot) -> MessageProcessor: ...


def get_processor(
    src_bot: Bot | str | None = None,
    dst_bot: Bot | None = None,
) -> type[MessageProcessor] | MessageProcessor:
    if dst_bot is not None:
        if not isinstance(src_bot, Bot):
            raise TypeError("src_bot must be Bot")
        return get_processor(src_bot)(src_bot, dst_bot)

    if isinstance(src_bot, Bot):
        src_bot = src_bot.type

    if src_bot in PROCESSORS:
        return PROCESSORS[src_bot]

    return PROCESSORS[None]  # common.MessageProcessor
