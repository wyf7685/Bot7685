import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterable, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, ClassVar, override
from weakref import WeakKeyDictionary

import anyio
import nonebot
import yarl
from nonebot.adapters import Event as BaseEvent
from nonebot.adapters.onebot.v11 import (
    ActionFailed,
    Adapter,
    Bot,
    Message,
    MessageEvent,
    MessageSegment,
)
from nonebot.compat import type_validate_python
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import uniseg as u

from src.plugins.gtg import call_soon
from src.plugins.upload_cos import upload_from_local, upload_from_url

from ..database import KVCacheDAO
from ..utils import (
    amr_to_mp3,
    async_client,
    check_url_ok,
    guess_url_type,
    solve_url_302,
)
from ._registry import converter, sender
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender


@converter(Adapter)
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
            self.logger.debug(f"获取 {self.src_bot} 平台: {platform}")

        return self.bot_platform_cache[self.src_bot]

    async def _get_api_rkey(self) -> tuple[str, str]:
        rkey_api = "https://llob.linyuchen.net/rkey"
        resp = await async_client().get(rkey_api)
        data: dict[str, str] = resp.json()
        p_rkey = data["private_rkey"].removeprefix("&rkey=")
        g_rkey = data["group_rkey"].removeprefix("&rkey=")
        self.logger.debug(f"从 API 获取 rkey: {p_rkey, g_rkey}")
        return p_rkey, g_rkey

    async def get_rkey(self) -> Sequence[str]:
        if "napcat" not in await self.get_platform():
            return await self._get_api_rkey()

        try:
            res = type_validate_python(
                list[dict[str, str]],
                await self.src_bot.call_api("nc_get_rkey"),
            )
        except Exception:
            self.logger.debug("nc_get_rkey 出错，使用 rkey API")
            return await self._get_api_rkey()

        rkeys = [item["rkey"].removeprefix("&rkey=") for item in res]
        self.logger.debug(f"从 NapCat 获取 rkey: {rkeys}")
        return rkeys

    async def check_rkey(self, url: str) -> str | None:
        if await check_url_ok(url):
            return url

        if "rkey" not in (parsed := yarl.URL(url)).query:
            return None

        for rkey in await self.get_rkey():
            updated = parsed.update_query(rkey=rkey).human_repr()
            if await check_url_ok(updated):
                self.logger.debug(f"更新 rkey: {url} -> {updated}")
                return updated

        return None

    async def url_to_image(self, url: str) -> u.Image | None:
        info = await guess_url_type(url)
        if info is None:
            return None

        name = f"{hash(url)}.{info.extension}"
        key = self.get_cos_key(name)

        try:
            url = await upload_from_url(url, key)
        except Exception as err:
            self.logger.opt(exception=err).debug("上传图片失败，使用原始链接")

        self.logger.debug(f"上传图片: {escape_tag(url)}")
        return u.Image(url=url, mimetype=info.mime, name=name)

    async def convert_image(self, url: str) -> u.Segment:
        if self.do_resolve_url:
            if (checked := await self.check_rkey(url)) and (
                seg := await self.url_to_image(checked)
            ):
                return seg
            return u.Text(f"[image:{url}]")

        return u.Image(url=url)

    async def cache_forward(
        self,
        forward_id: str,
        content: list[dict[str, Any]],
    ) -> bool:
        if not content:
            return False

        cache_data: list[dict[str, Any]] = []
        processor = MessageConverter(self.src_bot)
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
            self.logger.debug(f"缓存合并转发消息: {forward_id}")
            return True

        return False

    async def handle_forward(self, data: dict[str, Any]) -> AsyncIterable[u.Segment]:
        cached = False
        forward_id = data["id"]
        if "napcat" in await self.get_platform() and (content := data.get("content")):
            cached = await self.cache_forward(forward_id, content)
        yield u.Text(f"[forward:{forward_id}:cache={cached}]")
        if cached:
            btn = u.Button(
                "input",
                label="加载合并转发消息",
                text=f"/forward load {forward_id}",
            )
            yield u.Keyboard([btn])

    async def handle_json_msg(self, data: dict[str, Any]) -> AsyncIterable[u.Segment]:
        def default() -> u.Segment:
            return u.Text(f"[json消息:{data}]")

        meta = data.get("meta", {})
        if not meta:
            yield default()
            return

        # Bili share
        if "detail_1" in meta and meta["detail_1"]["title"] == "哔哩哔哩":
            detail = meta["detail_1"]
            url = await solve_url_302(detail["qqdocurl"])
            yield u.Text(f"[哔哩哔哩] {detail['desc']}\n{url}")
            yield u.Image(url=detail["preview"])
            return

        yield default()
        return

    async def url_to_video(self, url: str) -> u.Video | None:
        key = self.get_cos_key(f"{hash(url)}.mp4")

        try:
            url = await upload_from_url(url, key)
        except Exception as err:
            self.logger.opt(exception=err).debug("上传视频失败，使用原始链接")

        self.logger.debug(f"上传视频: {escape_tag(url)}")
        return u.Video(url=url)

    async def convert_video(self, url: str) -> u.Segment:
        if self.do_resolve_url:
            if (fixed := await self.check_rkey(url)) and (
                seg := await self.url_to_video(fixed)
            ):
                return seg
            return u.Text(f"[video:{url}]")

        return u.Video(url=url)

    async def upload_local_file(self, path: Path) -> u.File | None:
        key = self.get_cos_key(f"{hash(path)}/{path.name}")

        try:
            url = await upload_from_local(path, key)
        except Exception as err:
            self.logger.opt(exception=err).debug("上传文件失败")
            return None

        self.logger.debug(f"上传文件: {escape_tag(url)}")
        return u.File(url=url)

    @contextlib.asynccontextmanager
    async def convert_file(self, file_id: str) -> AsyncGenerator[u.Segment]:
        res = await self.src_bot.call_api("get_file", file_id=file_id)
        path = Path("/share/QQ/NapCat/temp") / str(res["file_name"])
        if path.exists():
            if seg := await self.upload_local_file(path):
                yield seg
            else:
                yield u.Text(f"[file:{file_id}]")
        path.unlink(missing_ok=True)

    async def convert_record(self, file_path: str) -> u.Segment:
        path = Path("/share") / Path(file_path).relative_to("/app/.config")

        agen = None
        if path.name.endswith(".amr"):
            if not path.exists():
                await anyio.sleep(1)
            if not path.exists():
                return u.Text(f"[record:{path.name}]")
            agen = aiter(amr_to_mp3(path))
            path = await anext(agen)

        seg = await self.upload_local_file(path)
        if seg is None:
            seg = u.Text(f"[record:{path}]")

        if agen is not None:
            with contextlib.suppress(StopAsyncIteration):
                await anext(agen)

        return seg

    @override
    async def convert_segment(
        self, segment: MessageSegment
    ) -> AsyncIterable[u.Segment]:
        match segment.type:
            case "at":
                yield u.Text(f"[at:{segment.data['qq']}]")
            case "image":
                if (url := segment.data.get("url")) and (
                    seg := await self.convert_image(url)
                ):
                    yield seg
            case "reply":
                yield await self.convert_reply(segment.data["id"])
            case "forward":
                async for seg in self.handle_forward(segment.data):
                    yield seg
            case "json":
                with contextlib.suppress(Exception):
                    json_data = json.loads(segment.data["data"])
                    async for seg in self.handle_json_msg(json_data):
                        yield seg
            case "video":
                if (url := segment.data.get("url")) and (
                    seg := await self.convert_video(url)
                ):
                    yield seg
            case "file":
                if file_id := segment.data.get("file_id"):
                    async with self.convert_file(file_id) as seg:
                        yield seg
            case "record":
                if (path := segment.data.get("path")) and (
                    seg := await self.convert_record(path)
                ):
                    yield seg
            case _:
                async for seg in super().convert_segment(segment):
                    yield seg


@sender(Adapter)
class MessageSender(BaseMessageSender[Bot, dict[str, Any]]):
    @override
    @staticmethod
    def extract_msg_id(data: dict[str, Any]) -> str:
        return str(data["message_id"]) if data else ""

    @staticmethod
    def _send_files(files: list[u.File], target: u.Target, bot: Bot) -> None:
        async def upload_file(file: u.File) -> None:
            try:
                await bot.call_api(
                    "upload_group_file",
                    group_id=int(target.id),
                    file=file.url,
                    name=file.name or file.id,
                )
            except ActionFailed as err:
                nonebot.logger.opt(exception=err).debug(f"上传群文件失败: {err}")
                await target.send(f"上传群文件失败: {file.id}", bot=bot)

        for file in files:
            if not file.url:
                continue
            call_soon(upload_file, file)

    @override
    @classmethod
    async def send(
        cls,
        dst_bot: Bot,
        target: u.Target,
        msg: u.UniMessage[u.Segment],
        src_type: str | None = None,
        src_id: str | None = None,
    ) -> None:
        # OneBot V11 适配器没有 Keyboard 消息段
        msg = msg.exclude(u.Keyboard)

        # 回复消息段应在消息头部，且仅有一个
        if u.Reply in msg:
            msg = msg[u.Reply, 0] + msg.exclude(u.Reply)

        # 文件消息段需要单独发送
        if files := msg[u.File]:
            msg = msg.exclude(u.File) + " ".join(
                f"[file:{file.name or file.id}]" for file in files
            )
            cls._send_files(files, target, dst_bot)

        # 发送消息
        await super().send(dst_bot, target, msg, src_type, src_id)
