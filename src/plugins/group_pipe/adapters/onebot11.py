import contextlib
import json
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, override
from weakref import WeakKeyDictionary

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
from src.plugins.upload_cos import upload_cos

from ..adapter import converts
from ..database import set_cache_value
from ..utils import async_client, check_url_ok, guess_url_type, solve_url_302
from .common import MessageConverter as BaseMessageConverter
from .common import MessageSender as BaseMessageSender

bot_platform_cache: WeakKeyDictionary[Bot, str] = WeakKeyDictionary()


class MessageConverter(
    BaseMessageConverter[MessageSegment, Bot, Message],
    adapter=Adapter.get_name(),
):
    do_resolve_url: bool = True

    @override
    @classmethod
    async def get_message(cls, event: BaseEvent) -> Message | None:
        if not isinstance(event, MessageEvent):
            return None

        return deepcopy(event.original_message)

    async def get_platform(self) -> str:
        if self.src_bot not in bot_platform_cache:
            data = await self.src_bot.get_version_info()
            platform = str(data.get("app_name", "unkown")).lower()
            bot_platform_cache[self.src_bot] = platform
            self.logger.debug(f"获取 {self.src_bot} 平台: {platform}")

        return bot_platform_cache[self.src_bot]

    async def _get_rkey_api(self) -> tuple[str, str]:
        rkey_api = "https://llob.linyuchen.net/rkey"
        resp = await async_client().get(rkey_api)
        data: dict[str, str] = resp.json()
        p_rkey = data["private_rkey"].removeprefix("&rkey=")
        g_rkey = data["group_rkey"].removeprefix("&rkey=")
        self.logger.debug(f"从 API 获取 rkey: {p_rkey, g_rkey}")
        return p_rkey, g_rkey

    async def _get_rkey_napcat(self) -> Iterable[str]:
        try:
            res = type_validate_python(
                list[dict[str, str]],
                await self.src_bot.call_api("nc_get_rkey"),
            )
        except Exception:
            self.logger.debug("Napcat nc_get_rkey 出错，使用 rkey API")
            return await self._get_rkey_api()

        rkeys = [item["rkey"].removeprefix("&rkey=") for item in res]
        self.logger.debug(f"从 NapCat 获取 rkey: {rkeys}")
        return rkeys

    async def _get_rkey_lagrange(self) -> Iterable[str]:
        try:
            res = type_validate_python(
                dict[str, list[dict[str, str]]],
                await self.src_bot.call_api("get_rkey"),
            )
        except Exception:
            self.logger.debug("Lagrange get_rkey 出错，使用 rkey API")
            return await self._get_rkey_api()

        rkeys = [item["rkey"].removeprefix("&rkey=") for item in res["rkeys"]]
        self.logger.debug(f"从 Lagrange 获取 rkey: {rkeys}")
        return rkeys

    async def get_rkey(self) -> Iterable[str]:
        platform = await self.get_platform()
        if "lagrange" in platform:
            return await self._get_rkey_lagrange()
        if "napcat" in platform:
            return await self._get_rkey_napcat()
        return await self._get_rkey_api()

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
            url = await upload_cos(url, key)
        except Exception as err:
            self.logger.opt(exception=err).debug("上传图片失败，使用原始链接")

        self.logger.debug(f"上传图片: {escape_tag(url)}")
        return u.Image(url=url, mimetype=info.mime, name=name)

    async def cache_forward(
        self,
        forward_id: str,
        content: list[dict[str, Any]],
    ) -> bool:
        if not content:
            return False

        cache_data: list[dict[str, object]] = []
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
            await set_cache_value(
                adapter=self.src_bot.type,
                key=f"forward_{forward_id}",
                value=json.dumps(cache_data),
            )
            self.logger.debug(f"缓存合并转发消息: {forward_id}")
            return True

        return False

    async def handle_json_msg(self, data: dict[str, Any]) -> list[u.Segment]:
        meta = data.get("meta", {})
        if not meta:
            return [u.Text(f"[json消息:{data}]")]

        # Bili share
        if "detail_1" in meta and meta["detail_1"]["title"] == "哔哩哔哩":
            detail = meta["detail_1"]
            url = await solve_url_302(detail["qqdocurl"])

            return [
                u.Text(f"[哔哩哔哩] {detail['desc']}\n{url}"),
                u.Image(url=detail["preview"]),
            ]

        return [u.Text(f"[json消息:{json.dumps(data)}]")]

    async def url_to_video(self, url: str) -> u.Video | None:
        key = self.get_cos_key(f"{hash(url)}.mp4")

        try:
            url = await upload_cos(url, key)
        except Exception as err:
            self.logger.opt(exception=err).debug("上传视频失败，使用原始链接")

        self.logger.debug(f"上传视频: {escape_tag(url)}")
        return u.Video(url=url)

    @converts("at")
    async def at(self, segment: MessageSegment) -> u.Segment:
        return u.Text(f"[at:{segment.data['qq']}]")

    @converts("image")
    async def image(self, segment: MessageSegment) -> u.Segment | None:
        if not (url := segment.data.get("url")):
            return None

        if self.do_resolve_url:
            if (checked := await self.check_rkey(url)) and (
                seg := await self.url_to_image(checked)
            ):
                return seg
            return u.Text(f"[image:{url}]")

        return u.Image(url=url)

    @converts("reply")
    async def reply(self, segment: MessageSegment) -> u.Segment:
        return await self.convert_reply(segment.data["id"])

    @converts("face")
    async def face(self, segment: MessageSegment) -> u.Segment:
        if isinstance((raw := segment.data.get("raw")), dict) and (
            text := raw.get("faceText")
        ):
            return u.Text(text)
        return u.Text(f"[face:{segment.data['id']}]")

    @converts("forward")
    async def forward(self, segment: MessageSegment) -> list[u.Segment]:
        cached = False
        forward_id: str = segment.data["id"]
        if "napcat" in await self.get_platform() and (
            content := segment.data.get("content")
        ):
            cached = await self.cache_forward(forward_id, content)

        segs: list[u.Segment] = [u.Text(f"[forward:{forward_id}:cache={cached}]")]
        if cached:
            btn = u.Button(
                "input",
                label="加载合并转发消息",
                text=f"/forward load {forward_id}",
            )
            segs.append(u.Keyboard([btn]))

        return segs

    @converts("json")
    async def json(self, segment: MessageSegment) -> list[u.Segment] | None:
        with contextlib.suppress(Exception):
            return await self.handle_json_msg(json.loads(segment.data["data"]))

    @converts("video")
    async def video(self, segment: MessageSegment) -> u.Segment | None:
        if not (url := segment.data.get("url")):
            return None

        if self.do_resolve_url:
            if (fixed := await self.check_rkey(url)) and (
                seg := await self.url_to_video(fixed)
            ):
                return seg
            return u.Text(f"[video:{url}]")

        return u.Video(url=url)


class MessageSender(
    BaseMessageSender[Bot, dict[str, object]],
    adapter=Adapter.get_name(),
):
    @override
    @staticmethod
    def extract_msg_id(data: dict[str, object]) -> str:
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
