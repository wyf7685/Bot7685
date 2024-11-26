from collections.abc import AsyncIterable
from typing import Any, cast

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

logger = nonebot.logger.opt(colors=True)


class MessageProcessor[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
]:
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None:
        self.src_bot = src_bot
        self.dst_bot = dst_bot

    @classmethod
    def get_message(cls, event: Event) -> TM | None:
        return cast(TM, event.get_message())

    @staticmethod
    def extract_msg_id(res: Any) -> str:
        return str(res)

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
                logger.opt(exception=err).warning("处理消息段失败")
                result.append(Text(f"[error:{segment.type}]"))
        return result

    @classmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: TB) -> list[str]:
        receipt = await msg.send(
            target=target,
            bot=dst_bot,
            fallback=FallbackStrategy.ignore,
        )
        return [cls.extract_msg_id(item) for item in receipt.msg_ids]
