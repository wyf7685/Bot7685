from collections.abc import AsyncGenerator
from typing import Any, cast

import httpx
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


async def download_file(url: str) -> bytes:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except (httpx.ConnectError, httpx.HTTPError):
            return b""
        else:
            return resp.read()


async def check_url_ok(url: str) -> bool:
    async with httpx.AsyncClient() as client, client.stream("GET", url) as resp:
        return resp.status_code == 200


class MessageProcessor[
    TMS: MessageSegment = MessageSegment,
    TB: Bot = Bot,
    TM: Message = Message,
]:
    def __init__(self, src_bot: TB, dst_bot: Bot | None = None) -> None:
        self.src_bot = src_bot
        self.dst_bot = dst_bot

    @staticmethod
    def get_message(event: Event) -> TM | None:
        return cast(TM, event.get_message())

    @staticmethod
    def extract_msg_id(res: Any) -> str:
        return str(res)

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

    async def convert_segment(self, segment: TMS) -> AsyncGenerator[Segment, None]:
        if fn := get_builder(self.src_bot):
            result = fn.convert(segment)
            if isinstance(result, list):
                for item in result:
                    yield item
            else:
                yield result

    async def process(self, msg: TM) -> UniMessage:
        if builder := get_builder(self.src_bot):
            msg = cast(TM, builder.preprocess(msg))

        result = UniMessage()
        for segment in msg:
            async for seg in self.convert_segment(segment):
                result.append(seg)

        return result

    @classmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: TB) -> list[str]:
        receipt = await msg.send(
            target=target,
            bot=dst_bot,
            fallback=FallbackStrategy.ignore,
        )
        return [cls.extract_msg_id(item) for item in receipt.msg_ids]
