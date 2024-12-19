import abc

from nonebot.adapters import Bot, Event, Message
from nonebot_plugin_alconna.uniseg import Segment, Target, UniMessage


class MessageConverter[TB: Bot, TM: Message](abc.ABC):
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


class MessageSender[TB: Bot](abc.ABC):
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
