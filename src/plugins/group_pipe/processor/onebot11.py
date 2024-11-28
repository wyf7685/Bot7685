import contextlib
import json
from collections.abc import AsyncIterable, Callable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, override
from weakref import WeakKeyDictionary

import nonebot
import yarl
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.onebot.v11 import (
    ActionFailed,
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.compat import type_validate_python
from nonebot.utils import escape_tag
from nonebot_plugin_alconna.uniseg import (
    Button,
    File,
    Image,
    Keyboard,
    Reply,
    Segment,
    Target,
    Text,
    UniMessage,
    Video,
)

from src.plugins.gtg import call_soon
from src.plugins.upload_cos import upload_from_local, upload_from_url

from ..database import KVCacheDAO
from ..utils import async_client, check_url_ok, guess_url_type
from ._registry import register
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

logger = nonebot.logger.opt(colors=True)


async def get_rkey() -> tuple[str, str]:
    rkey_api = "https://llob.linyuchen.net/rkey"
    resp = await async_client().get(rkey_api)
    data: dict[str, str] = resp.json()
    p_rkey = data["private_rkey"].removeprefix("&rkey=")
    g_rkey = data["group_rkey"].removeprefix("&rkey=")
    logger.debug(f"从 API 获取 rkey: {p_rkey, g_rkey}")
    return p_rkey, g_rkey


async def url_to_image(
    url: str,
    get_cos_key: Callable[[str], str] | None = None,
) -> Image | None:
    info = await guess_url_type(url)
    if info is None:
        return None

    name = f"{hash(url)}.{info.extension}"
    key = get_cos_key(name) if get_cos_key else name

    try:
        url = await upload_from_url(url, key)
    except Exception as err:
        logger.opt(exception=err).debug("上传图片失败，使用原始链接")
    else:
        logger.debug(f"上传图片: {escape_tag(url)}")

    return Image(url=url, mimetype=info.mime)


async def url_to_video(
    url: str,
    get_cos_key: Callable[[str], str] | None = None,
) -> Video | None:
    key = f"{hash(url)}.mp4"
    if get_cos_key:
        key = get_cos_key(key)

    try:
        url = await upload_from_url(url, key)
    except Exception as err:
        logger.opt(exception=err).debug("上传视频失败，使用原始链接")
    else:
        logger.debug(f"上传视频: {escape_tag(url)}")

    return Video(url=url)


async def upload_local_file(
    path: Path,
    get_cos_key: Callable[[str], str] | None = None,
) -> File | None:
    key = f"{hash(path)}/{path.name}"
    if get_cos_key:
        key = get_cos_key(key)
    try:
        url = await upload_from_local(path, key)
    except Exception as err:
        logger.opt(exception=err).debug("上传文件失败")
        return None
    else:
        logger.debug(f"上传文件: {escape_tag(url)}")
        return File(url=url)


async def solve_url_302(url: str) -> str:
    async with async_client().stream("GET", url) as resp:
        if resp.status_code == 302:
            return await solve_url_302(resp.headers["Location"].partition("?")[0])
    return url


async def handle_json_msg(data: dict[str, Any]) -> AsyncIterable[Segment]:
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


class MessageConverter(BaseMessageConverter[MessageSegment, Bot, Message]):
    bot_platform_cache: ClassVar[WeakKeyDictionary[Bot, str]] = WeakKeyDictionary()
    do_resolve_url: bool = True

    @override
    @classmethod
    def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        return deepcopy(event.original_message)

    async def get_platform(self) -> str:
        if self.src_bot not in self.bot_platform_cache:
            data = await self.src_bot.get_version_info()
            platform = str(data.get("app_name", "unkown")).lower()
            self.bot_platform_cache[self.src_bot] = platform
            logger.debug(f"获取 {self.src_bot} 平台: {platform}")

        return self.bot_platform_cache[self.src_bot]

    async def get_rkey(self) -> Sequence[str]:
        if "napcat" not in await self.get_platform():
            return await get_rkey()

        try:
            res = type_validate_python(
                list[dict[str, str]],
                await self.src_bot.call_api("nc_get_rkey"),
            )
        except Exception:
            logger.debug("nc_get_rkey 出错，使用 rkey API")
            return await get_rkey()

        rkeys = [item["rkey"].removeprefix("&rkey=") for item in res]
        logger.debug(f"从 NapCat 获取 rkey: {rkeys}")
        return rkeys

    async def check_rkey(self, url: str) -> str | None:
        if await check_url_ok(url):
            return url

        if "rkey" in (parsed := yarl.URL(url)).query:
            for rkey in await self.get_rkey():
                updated = parsed.update_query(rkey=rkey).human_repr()
                if await check_url_ok(updated):
                    logger.debug(f"更新 rkey: {url} -> {updated}")
                    return updated

        return None

    async def cache_forward(
        self,
        forward_id: str,
        content: list[dict[str, Any]],
    ) -> bool:
        if not content:
            return False

        cache_data: list[dict[str, Any]] = []
        processor = MessageProcessor(self.src_bot)
        processor.do_resolve_url = False

        for item in content:
            sender: dict[str, str] = item.get("sender", {})
            msg = item.get("message")
            if not msg:
                continue
            nick = (
                sender.get("card")
                or sender.get("nickname")
                or sender.get("user_id")
                or ""
            )

            msg = Message([MessageSegment(**seg) for seg in msg])
            unimsg = await processor.convert(msg)
            cache_data.append({"nick": nick, "msg": unimsg.dump(media_save_dir=False)})

        if cache_data:
            await KVCacheDAO().set_value(
                adapter=self.src_bot.type,
                key=f"forward_{forward_id}",
                value=json.dumps(cache_data),
            )
            return True

        return False

    async def handle_forward(self, data: dict[str, Any]) -> AsyncIterable[Segment]:
        cached = False
        forward_id = data["id"]
        if "napcat" in await self.get_platform() and (content := data.get("content")):
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
    async def convert_segment(self, segment: MessageSegment) -> AsyncIterable[Segment]:
        match segment.type:
            case "at":
                yield Text(f"[at:{segment.data['qq']}]")
            case "image":
                if url := segment.data.get("url"):
                    if self.do_resolve_url:
                        if (url := await self.check_rkey(url)) and (
                            seg := await url_to_image(url, self.get_cos_key)
                        ):
                            yield seg
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
                if url := segment.data.get("url"):
                    if self.do_resolve_url:
                        if (url := await self.check_rkey(url)) and (
                            seg := await url_to_video(url, self.get_cos_key)
                        ):
                            yield seg
                    else:
                        yield Video(url=url)
            case "file":
                if file_id := segment.data.get("file_id"):
                    res = await self.src_bot.call_api("get_file", file_id=file_id)
                    path = Path("/share") / str(res["file_name"])
                    if path.exists():
                        if seg := await upload_local_file(path, self.get_cos_key):
                            yield seg
                        else:
                            yield Text(f"[file:{file_id}]")
                    path.unlink(missing_ok=True)
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg


class MessageSender(BaseMessageSender[Bot, dict[str, Any]]):
    @override
    @staticmethod
    def extract_msg_id(data: dict[str, Any]) -> str:
        return str(data["message_id"]) if data else ""

    @staticmethod
    def _send_files(files: list[File], target: Target, bot: Bot) -> None:
        async def upload_file(file: File) -> None:
            try:
                await bot.call_api(
                    "upload_group_file",
                    group_id=int(target.id),
                    file=file.url,
                    name=file.name or file.id,
                )
            except ActionFailed as err:
                logger.opt(exception=err).debug(f"上传群文件失败: {err}")
                await UniMessage.text(f"上传群文件失败: {file.id}").send(target, bot)

        for file in files:
            if not file.url:
                continue
            call_soon(upload_file, file)

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: Bot,
        target: Target,
        msg: UniMessage[Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        # OneBot V11 适配器没有 Keyboard 消息段
        msg = msg.exclude(Keyboard)

        # 回复消息段应在消息头部，且仅有一个
        if Reply in msg:
            msg = msg[Reply, 0] + msg.exclude(Reply)

        # 文件消息段需要单独发送
        if files := msg[File]:
            msg = msg.exclude(File) + " ".join(
                f"[file:{file.name or file.id}]" for file in files
            )
            cls._send_files(files, target, dst_bot)

        # 发送消息
        return await super().send(dst_bot, target, msg, src_type, src_id)


@register("OneBot V11")
class MessageProcessor(MessageConverter, MessageSender): ...
