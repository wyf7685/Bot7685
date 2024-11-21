import contextlib
import json
from collections.abc import AsyncGenerator
from copy import deepcopy
from typing import Any, ClassVar, override
from weakref import WeakKeyDictionary

import fleep
import httpx
import yarl
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot_plugin_alconna.uniseg import (
    Button,
    Image,
    Keyboard,
    Reply,
    Segment,
    Target,
    Text,
    UniMessage,
    Video,
)

from ..database import KVCacheDAO
from .common import MessageProcessor as BaseMessageProcessor
from .common import check_url_ok, download_file


async def get_rkey() -> tuple[str, str]:
    rkey_api = "https://llob.linyuchen.net/rkey"
    async with httpx.AsyncClient() as client:
        resp = await client.get(rkey_api)
        data = resp.json()
        return data["private_rkey"], data["group_rkey"]


async def url_to_image(url: str) -> Image:
    if raw := await download_file(url):
        return Image(url=url, raw=raw, mimetype=fleep.get(raw).mime[0])

    if "rkey" in (parsed := yarl.URL(url)).query:
        for rkey in await get_rkey():
            updated = parsed.update_query(rkey=rkey).human_repr()
            if raw := await download_file(parsed.update_query(rkey=rkey).human_repr()):
                return Image(url=updated, raw=raw, mimetype=fleep.get(raw).mime[0])

    return Image(url=url)


async def url_to_video(url: str) -> Video:
    if await check_url_ok(url):
        return Video(url=url)

    if "rkey" in (parsed := yarl.URL(url)).query:
        for rkey in await get_rkey():
            updated = parsed.update_query(rkey=rkey).human_repr()
            if await check_url_ok(url):
                return Video(url=updated)

    return Video(url=url)


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
    bot_platform_cache: ClassVar[WeakKeyDictionary[Bot, str]] = WeakKeyDictionary()
    do_download_image: bool

    @override
    def __init__(self, src_bot: Bot, dst_bot: BaseBot | None = None) -> None:
        super().__init__(src_bot, dst_bot)
        self.do_download_image = True

    @override
    @staticmethod
    def get_message(event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        return deepcopy(event.original_message)

    @override
    @staticmethod
    def extract_msg_id(msg_ids: list[dict[str, Any]]) -> str:
        return str(msg_ids[0]["message_id"]) if msg_ids else ""

    async def get_platform(self) -> str:
        if self.src_bot not in self.bot_platform_cache:
            data = await self.src_bot.get_version_info()
            platform = str(data.get("app_name", "unkown")).lower()
            self.bot_platform_cache[self.src_bot] = platform

        return self.bot_platform_cache[self.src_bot]

    async def cache_forward(self, id_: str, content: list[dict[str, Any]]) -> bool:
        if not content:
            return False

        cache_data: list[dict[str, Any]] = []
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

            msg = Message([MessageSegment(**seg) for seg in msg])
            unimsg = await processor.process(msg)
            cache_data.append({"nick": nick, "msg": unimsg.dump(media_save_dir=False)})

        if cache_data:
            key = f"forward_{id_}"
            value = json.dumps(cache_data)
            await KVCacheDAO().set_value(self.src_bot.type, key, value)
            return True

        return False

    async def handle_forward(
        self, data: dict[str, Any]
    ) -> AsyncGenerator[Segment, None]:
        cached = False
        forward_id = data["id"]
        if "napcat" in await self.get_platform() and "content" in data:
            content = data["content"]
            cached = await self.cache_forward(forward_id, content)
        yield Text(f"[forward:{forward_id}:cache={cached}]")
        if cached:
            btn = Button(
                "input",
                label="加载合并转发消息",
                text=f"/forward load {forward_id}",
            )
            yield Keyboard([btn])

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
                async for seg in self.handle_forward(segment.data):
                    yield seg
            case "json":
                with contextlib.suppress(Exception):
                    json_data = json.loads(segment.data["data"])
                    async for seg in handle_json_msg(json_data):
                        yield seg
            case "video":
                yield await url_to_video(url=segment.data["url"])
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg

    @override
    @classmethod
    async def send(cls, msg: UniMessage, target: Target, dst_bot: Bot) -> list[str]:
        msg = msg.exclude(Keyboard)
        if Reply in msg:
            msg = msg.include(Reply) + msg.exclude(Reply)
        return await super().send(msg, target, dst_bot)
