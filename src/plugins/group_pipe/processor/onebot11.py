import contextlib
import json
from collections.abc import AsyncGenerator
from typing import Any, override

import httpx
import yarl
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot_plugin_alconna.uniseg import Image, Segment, Text

from ..database import KVCacheDAO
from .common import MessageProcessor as BaseMessageProcessor
from .common import download_file


async def get_rkey() -> tuple[str, str]:
    rkey_api = "https://llob.linyuchen.net/rkey"
    async with httpx.AsyncClient() as client:
        resp = await client.get(rkey_api)
        data = resp.json()
        return data["private_rkey"], data["group_rkey"]


async def url_to_image(url: str) -> Image:
    if raw := await download_file(url):
        return Image(raw=raw)

    parsed = yarl.URL(url)
    if "rkey" not in parsed.query:
        return Image(url=url)

    for rkey in await get_rkey():
        if raw := await download_file(parsed.update_query(rkey=rkey).human_repr()):
            return Image(raw=raw)

    return Image(url=url)


async def solve_url_302(url: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        if resp.status_code == 302:
            return resp.headers["Location"].partition("?")[0]
        return url


async def handle_json_msg(data: dict[str, Any]) -> AsyncGenerator[Segment, None]:
    def default() -> Segment:
        return Text(f"[json消息:{data}]")

    meta = data.get("meta", {})
    if not meta:
        yield default()
        return

    # Bili share
    if "detail_1" in meta and meta["detail_1"]["title"] == "哔哩哔哩":
        detail = meta["detail_1"]
        url = await solve_url_302(detail["qqdocurl"])
        yield Text(f"[哔哩哔哩] {detail['desc']}\n{url}")
        yield Image(url=detail["preview"])
        return

    yield default()
    return


class MessageProcessor(BaseMessageProcessor[MessageSegment, Bot, Message]):
    def __init__(self, src_bot: Bot, dst_bot: BaseBot | None = None) -> None:
        super().__init__(src_bot, dst_bot)
        self.do_download_image = True

    @override
    @staticmethod
    def get_message(event: BaseEvent) -> Message:
        assert isinstance(event, MessageEvent)  # noqa: S101
        return event.original_message

    @override
    @staticmethod
    async def extract_msg_id(msg_ids: list[dict[str, Any]]) -> str:
        return str(msg_ids[0]["message_id"]) if msg_ids else ""

    async def get_platform(self) -> str:
        data = await self.src_bot.get_version_info()
        return str(data.get("app_name", "unkown")).lower()

    async def cache_forward(self, id_: str, content: list[dict[str, Any]]) -> bool:
        if not content:
            return False

        cache_data = []
        processor = MessageProcessor(self.src_bot)
        processor.do_download_image = False

        for item in content:
            sender: dict[str, str] = item.get("sender", {})
            nick = (
                sender.get("card")
                or sender.get("nickname")
                or sender.get("user_id")
                or ""
            )
            msg = item.get("message")
            if not msg:
                continue

            unimsg = await processor.process(
                Message([MessageSegment(**seg) for seg in msg])
            )
            cache_data.append({"nick": nick, "msg": unimsg.dump(media_save_dir=False)})

        if cache_data:
            await KVCacheDAO().set_value(self.src_bot.type, id_, json.dumps(cache_data))
            return True

        return False

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncGenerator[Segment, None]:
        match segment.type:
            case "at":
                yield Text(f"[at:{segment.data['qq']}]")
            case "image":
                if url := segment.data.get("url"):
                    if self.do_download_image:
                        yield await url_to_image(url)
                    else:
                        yield Image(url=url)
            case "reply":
                yield await self.convert_reply(segment.data["id"])
            case "forward":
                cached = False
                if "napcat" in await self.get_platform() and "content" in segment.data:
                    cached = await self.cache_forward(
                        segment.data["id"],
                        segment.data["content"],
                    )
                yield Text(f"[合并转发:{segment.data['id']}:cache={cached}]")
            case "json":
                with contextlib.suppress(Exception):
                    json_data = json.loads(segment.data["data"])
                    async for seg in handle_json_msg(json_data):
                        yield seg
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg
