from collections.abc import AsyncIterable
from typing import TYPE_CHECKING, Any, ClassVar, cast, override

import nonebot
from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna import uniseg as u

from ..adapter import MessageConverter as AbstractMessageConverter
from ..adapter import MessageSender as AbstractMessageSender
from ..database import MsgIdCacheDAO

if TYPE_CHECKING:
    import loguru


class MessageConverter[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
](AbstractMessageConverter[TB, TM]):
    _adapter_: ClassVar[str | None] = None
    logger: ClassVar["loguru.Logger"] = nonebot.logger.opt(colors=True)

    @override
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None:
        self.src_bot: TB = src_bot
        self.dst_bot: Bot | None = dst_bot

    @override
    @classmethod
    def get_message(cls, event: Event) -> TM | None:
        return cast("TM", event.get_message())

    @override
    @classmethod
    def get_message_id(cls, event: Event, bot: TB) -> str:
        return u.get_message_id(event, bot)

    def get_cos_key(self, key: str) -> str:
        type_ = self.src_bot.type.lower().replace(" ", "_")
        return f"{type_}/{self.src_bot.self_id}/{key}"

    async def get_reply_id(self, message_id: str) -> str | None:
        if self.dst_bot is None:
            return None

        get_reply_id = MsgIdCacheDAO().get_reply_id
        return await get_reply_id(
            src_adapter=self.src_bot.type,
            dst_adapter=self.dst_bot.type,
            src_id=message_id,
        ) or await get_reply_id(
            src_adapter=self.dst_bot.type,
            dst_adapter=self.src_bot.type,
            dst_id=message_id,
        )

    async def convert_reply(self, src_msg_id: str | int) -> u.Segment:
        if reply_id := await self.get_reply_id(str(src_msg_id)):
            return u.Reply(reply_id)
        return u.Text(f"[reply:{src_msg_id}]")

    async def _convert_default(self, segment: TMS) -> AsyncIterable[u.Segment]:
        if fn := u.get_builder(self.src_bot):
            result = fn.convert(segment)
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result

    @override
    async def convert(self, msg: TM) -> u.UniMessage[u.Segment]:
        if builder := u.get_builder(self.src_bot):
            msg = cast("TM", builder.preprocess(msg))

        result = u.UniMessage[u.Segment]()
        segment: TMS
        for segment in msg:
            fn = self._find_fn(segment) or self._convert_default

            try:
                async for seg in fn(segment):
                    result.append(seg)
            except Exception as err:
                self.logger.opt(exception=err).warning("处理消息段失败")
                result.append(u.Text(f"[error:{segment.type}]"))
        return result


class MessageSender[TB: Bot, TR: Any](AbstractMessageSender[TB]):
    _adapter_: ClassVar[str | None] = None

    @staticmethod
    def extract_msg_id(data: TR) -> str:
        return str(data)

    @classmethod
    async def set_dst_id(
        cls,
        src_adapter: str | None,
        src_id: str | None,
        dst_bot: TB,
        data: TR,
    ) -> None:
        if src_adapter and src_id:
            await MsgIdCacheDAO().set_dst_id(
                src_adapter=src_adapter,
                src_id=src_id,
                dst_adapter=dst_bot.type,
                dst_id=cls.extract_msg_id(data),
            )

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: TB,
        target: u.Target,
        msg: u.UniMessage[u.Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        receipt = await msg.send(
            target=target,
            bot=dst_bot,
            fallback=u.FallbackStrategy.ignore,
        )

        for item in receipt.msg_ids:
            await cls.set_dst_id(
                src_adapter=src_type,
                src_id=src_id,
                dst_bot=dst_bot,
                data=item,
            )
