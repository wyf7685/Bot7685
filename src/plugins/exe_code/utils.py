from typing import Any, ClassVar, Dict, Iterable, Optional, Self

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.segment import At as UniAt
from nonebot_plugin_alconna.uniseg.segment import Image as UniImage
from nonebot_plugin_alconna.uniseg.segment import Text as UniText
from nonebot_plugin_saa import AggregatedMessageFactory
from nonebot_plugin_saa import Image as SaaImage
from nonebot_plugin_saa import Mention as SaaMention
from nonebot_plugin_saa import MessageFactory, MessageSegmentFactory, PlatformTarget
from nonebot_plugin_saa import Text as SaaText

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


async def as_unimsg(
    bot: Bot, event: Event, message: T_Message | MessageFactory
) -> UniMessage:
    msg_cls = event.get_message().__class__

    if isinstance(message, MessageFactory):
        message = msg_cls([await seg.build(bot) for seg in message])
    elif isinstance(message, MessageSegment):
        message = msg_cls([message])

    if isinstance(message, (str, UniSegment)):
        message = UniMessage(message)
    elif isinstance(message, Message):
        message = await UniMessage.generate(message=message)

    return message


def uniseg2msf(uniseg: UniSegment) -> MessageSegmentFactory:

    if isinstance(uniseg, UniText):
        return SaaText(uniseg.text)
    elif isinstance(uniseg, UniImage):
        return SaaImage(uniseg.id or uniseg.url or uniseg.path or uniseg.raw or b"")
    elif isinstance(uniseg, UniAt):
        return SaaMention(uniseg.target)
    else:
        return SaaText(f"[{uniseg.type}]")


def uni2saa(message: UniMessage | UniSegment) -> MessageFactory:
    if isinstance(message, UniSegment):
        return MessageFactory(uniseg2msf(message))

    return MessageFactory(uniseg2msf(seg) for seg in message)


async def as_msgfac(
    bot: Bot, event: Event, message: T_Message | MessageFactory
) -> MessageFactory:
    if isinstance(message, MessageFactory):
        return message
    message = await as_unimsg(bot, event, message)
    return uni2saa(message)


async def send_message(
    bot: Bot,
    event: Event,
    target: Optional[Target],
    message: T_Message | MessageFactory,
) -> Receipt:
    message = await as_unimsg(bot, event, message)
    return await message.send(target or event, bot)


async def send_forward_message(
    bot: Bot,
    event: Event,
    target: Optional[PlatformTarget],
    msgs: Iterable[T_Message],
):
    amf = AggregatedMessageFactory([await as_msgfac(bot, event, msg) for msg in msgs])

    if target is None:
        await amf.send()
    else:
        await amf.send_to(target, bot)
