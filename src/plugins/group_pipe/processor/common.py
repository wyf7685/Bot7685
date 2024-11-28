from collections.abc import AsyncIterable
from typing import Any, ClassVar, cast, override
from weakref import WeakKeyDictionary

import anyio
import nonebot
from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import (
    FallbackStrategy,
    Reply,
    Segment,
    Target,
    Text,
    UniMessage,
    get_builder,
)

from ..database import MsgIdCacheDAO
from ._registry import register
from .abstract import (
    AbstractMessageConverter,
    AbstractMessageProcessor,
    AbstractMessageSender,
)


class MessageConverter[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
](AbstractMessageConverter[TMS, TB, TM]):
    logger = nonebot.logger.opt(colors=True)

    @override
    @classmethod
    def get_message(cls, event: Event) -> TM | None:
        return cast(TM, event.get_message())

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

    async def convert_reply(self, src_msg_id: str | int) -> Segment:
        if reply_id := await self.get_reply_id(str(src_msg_id)):
            return Reply(reply_id)
        return Text(f"[reply:{src_msg_id}]")

    async def convert_segment(self, segment: TMS) -> AsyncIterable[Segment]:
        if fn := get_builder(self.src_bot):
            result = fn.convert(segment)
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result

    @override
    async def process(self, msg: TM) -> UniMessage[Segment]:
        if builder := get_builder(self.src_bot):
            msg = cast(TM, builder.preprocess(msg))

        result = UniMessage[Segment]()
        segment: TMS
        for segment in msg:
            try:
                async for seg in self.convert_segment(segment):
                    result.append(seg)
            except Exception as err:
                self.logger.opt(exception=err).warning("处理消息段失败")
                result.append(Text(f"[error:{segment.type}]"))
        return result


class MessageSender[TB: Bot, TR = Any](AbstractMessageSender[TB]):
    _bot_send_lock: ClassVar[WeakKeyDictionary[Bot, anyio.Lock]] = WeakKeyDictionary()

    @classmethod
    def _send_lock(cls, dst_bot: Bot) -> anyio.Lock:
        if lock := cls._bot_send_lock.get(dst_bot):
            return lock

        lock = cls._bot_send_lock[dst_bot] = anyio.Lock()
        return lock

    @staticmethod
    def extract_msg_id(data: TR) -> str:
        return str(data)

    @classmethod
    async def _set_dst_id(
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
        target: Target,
        msg: UniMessage,
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        async with cls._send_lock(dst_bot):
            receipt = await msg.send(
                target=target,
                bot=dst_bot,
                fallback=FallbackStrategy.ignore,
            )
        for item in receipt.msg_ids:
            await cls._set_dst_id(
                src_adapter=src_type,
                src_id=src_id,
                dst_bot=dst_bot,
                data=item,
            )


@register(None)
class MessageProcessor(
    MessageConverter[MessageSegment, Bot, Message],
    MessageSender[Bot],
    AbstractMessageProcessor[MessageSegment, Bot, Message],
): ...
