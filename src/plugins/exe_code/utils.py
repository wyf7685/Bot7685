from typing import Any, ClassVar, Dict, Iterable, Optional, Self

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.segment import CustomNode
from nonebot_plugin_alconna.uniseg.segment import Reference

from .const import T_API_Result, T_Message


class Result:
    error: Optional[Exception] = None
    _data: T_API_Result

    def __init__(self, data: T_API_Result):
        self._data = data
        if isinstance(data, dict) and "error" in data:
            self.error = data["error"]

    def __getitem__(self, key: str | int):
        return self._data.__getitem__(key)  # type: ignore

    def __getattribute__(self, name: str) -> Any:
        if isinstance(self._data, dict) and name in self._data:
            return self._data[name]
        return super(Result, self).__getattribute__(name)

    def __repr__(self) -> str:
        if self.error is not None:
            return f"<Result error={self.error!r}>"
        return f"<Result data={self._data}>"


class Buffer:
    _user_buf: ClassVar[Dict[str, Self]] = {}
    _buffer: str

    def __new__(cls, uin: str) -> Self:
        if uin not in cls._user_buf:
            buf = super(Buffer, cls).__new__(cls)
            buf._buffer = ""
            cls._user_buf[uin] = buf
        return cls._user_buf[uin]

    def write(self, text: str) -> None:
        assert isinstance(text, str)
        self._buffer += text

    def getvalue(self) -> str:
        value, self._buffer = self._buffer, ""
        return value


def check_message_t(message: Any) -> bool:
    return isinstance(message, (str, Message, MessageSegment, UniMessage, UniSegment))


async def as_unimsg(event: Event, message: T_Message) -> UniMessage:
    msg_cls = type(event.get_message())

    if isinstance(message, MessageSegment):
        message = msg_cls([message])
    if isinstance(message, (str, UniSegment)):
        message = UniMessage(message)
    elif isinstance(message, Message):
        message = await UniMessage.generate(message=message)

    return message


async def send_forward_message(
    bot: Bot,
    event: Event,
    target: Optional[Target],
    msgs: Iterable[T_Message],
) -> Receipt:
    return await send_message(
        bot,
        event,
        target,
        Reference(nodes=[CustomNode("", "", await as_unimsg(event, i)) for i in msgs]),
    )


async def send_message(
    bot: Bot,
    event: Event,
    target: Optional[Target],
    message: T_Message,
) -> Receipt:
    message = await as_unimsg(event, message)
    return await message.send(target or event, bot)
