import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any, override

import httpx
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot_plugin_alconna.uniseg import Image, Reply, Segment, Text

from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


async def solve_url_302(url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code == 302:
            return resp.headers["Location"].partition("?")[0]
        return url


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    @override
    @staticmethod
    def get_message(event: Event) -> Message:
        assert isinstance(event, MessageEvent)  # noqa: S101
        return event.original_message

    @override
    @staticmethod
    async def extract_msg_id(msg_ids: list[dict[str, Any]]) -> str:
        return str(msg_ids[0]["message_id"]) if msg_ids else ""

    async def handle_json_msg(
        self, data: dict[str, Any]
    ) -> AsyncGenerator[Segment, None]:
        def default() -> Segment:
            return Text(f"[json消息:{data}]")

        meta = data.get("meta", {})
        if not meta:
            yield default()
            return

        # Bilibili share
        if "detail_1" in meta and meta["detail_1"]["title"] == "哔哩哔哩":
            detail = meta["detail_1"]
            url = await solve_url_302(detail["qqdocurl"])
            yield Text(f"[哔哩哔哩] {detail['desc']}\n{url}")
            yield Image(url=detail["preview"])
            return

        yield default()

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "at":
                yield Text(f"[at:{segment.data['qq']}]")
            case "image":
                if url := segment.data.get("url"):
                    yield (
                        Image(raw=raw)
                        if (raw := await download_file(url))
                        else Image(url=url)
                    )
            case "reply":
                msg_id = str(segment.data["id"])
                if reply_id := await self.get_reply_id(msg_id):
                    yield Reply(reply_id)
            case "forward":
                yield Text(f"[合并转发:{segment.data['id']}]")
            case "json":
                with contextlib.suppress(Exception):
                    json_data = json.loads(segment.data["data"])
                    async for seg in self.handle_json_msg(json_data):
                        yield seg
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg
