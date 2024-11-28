import abc
from collections.abc import AsyncIterable

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment, Target, UniMessage


class AbstractMessageConverter[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
](abc.ABC):
    src_bot: TB
    dst_bot: Bot | None

    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None:
        self.src_bot = src_bot
        self.dst_bot = dst_bot

    @classmethod
    @abc.abstractmethod
    def get_message(cls, event: Event) -> TM | None:
        return NotImplemented

    @abc.abstractmethod
    async def convert_segment(self, segment: TMS) -> AsyncIterable[Segment]:
        yield NotImplemented

    @abc.abstractmethod
    async def process(self, msg: TM) -> UniMessage[Segment]:
        return NotImplemented


class AbstractMessageSender[TB: Bot = Bot](abc.ABC):
    @classmethod
    @abc.abstractmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: TB) -> list[str]:
        return NotImplemented


class AbstractMessageProcessor[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
](
    AbstractMessageSender[TB],
    AbstractMessageConverter[TMS, TB, TM],
): ...
