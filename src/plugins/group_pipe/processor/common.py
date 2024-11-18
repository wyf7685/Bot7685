from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot.internal.matcher import current_bot
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
    def __init__(self, dst_adapter: str) -> None:
        self.dst_adapter = dst_adapter

    @staticmethod
    def get_bot() -> TB:
        return cast(TB, current_bot.get())

    @staticmethod
    def get_message(event: Event) -> TM:
        return cast(TM, event.get_message())

    @staticmethod
    async def extract_msg_id(msg_ids: list[Any]) -> str:  # noqa: ARG004
        return ""

    async def get_dst_id(self, src_id: str) -> str | None:
        return await MsgIdCacheDAO().get_dst_id(
            src_adapter=self.get_bot().type,
            src_id=src_id,
            dst_adapter=self.dst_adapter,
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
