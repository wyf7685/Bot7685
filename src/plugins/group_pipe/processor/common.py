from collections.abc import AsyncGenerator
from typing import cast

import httpx
from nonebot.adapters import Bot, Message, MessageSegment
from nonebot.internal.matcher import current_bot
from nonebot_plugin_alconna.uniseg import Segment, UniMessage, get_builder


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
    @staticmethod
    def get_bot() -> TB:
        return cast(TB, current_bot.get())

    @classmethod
    async def process_segment(cls, segment: TMS) -> AsyncGenerator[Segment, None]:
        if fn := get_builder(cls.get_bot()):
            result = fn.convert(segment)
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result

    @classmethod
    async def process(cls, msg: TM) -> UniMessage:
        result = UniMessage()
        if fn := get_builder(cls.get_bot()):
            msg = cast(TM, fn.preprocess(msg))

        for segment in msg:
            async for seg in cls.process_segment(segment):
                result.append(seg)

        return result
