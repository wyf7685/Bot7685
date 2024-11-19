from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot_plugin_alconna.uniseg import Segment, UniMessage, get_builder

from ..database import MsgIdCacheDAO


async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError):
            return b""
        else:
            return resp.read()


class MessageProcessor[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
]:
    def __init__(self, src_bot: TB, dst_bot: Bot) -> None:
        self.src_bot = src_bot
        self.dst_bot = dst_bot

    def get_bot(self) -> TB:
        return self.src_bot

    @staticmethod
    def get_message(event: Event) -> TM:
        return cast(TM, event.get_message())

    @staticmethod
    async def extract_msg_id(msg_ids: list[Any]) -> str:
        return str(msg_ids[0]) if msg_ids else ""

    async def get_reply_id(self, message_id: str) -> str | None:
        return await MsgIdCacheDAO().get_reply_id(
            src_adapter=self.get_bot().type,
            dst_adapter=self.dst_bot.type,
            src_id=message_id,
        ) or await MsgIdCacheDAO().get_reply_id(
            src_adapter=self.dst_bot.type,
            dst_adapter=self.get_bot().type,
            dst_id=message_id,
        )

    async def convert_segment(self, segment: TMS) -> AsyncGenerator[Segment, None]:
        if fn := get_builder(self.get_bot()):
            result = fn.convert(segment)
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result

    async def process(self, msg: TM) -> UniMessage:
        result = UniMessage()
        if fn := get_builder(self.get_bot()):
            msg = cast(TM, fn.preprocess(msg))

        for segment in msg:
            async for seg in self.convert_segment(segment):
                result.append(seg)

        return result
