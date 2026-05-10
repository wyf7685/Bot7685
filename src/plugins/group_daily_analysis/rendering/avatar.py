"""头像获取、下载、校验与缓存。"""

import asyncio
import base64
import functools
from typing import TYPE_CHECKING

import httpx
from nonebot.log import logger
from nonebot.utils import escape_tag

from src.service.cache import get_cache

from .avatar_reuse import ReusableAvatarManager

if TYPE_CHECKING:
    from nonebot_plugin_uninfo import User
    from nonebot_plugin_uninfo.params import Interface

MAX_CONCURRENT_DOWNLOADS = 10

# url -> base64 data uri
_avatar_cache = get_cache[str]("group_daily_avatar", pickle=False)

_download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


@functools.cache
def get_default_avatar_base64() -> str:
    svg = (
        '<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="50" cy="50" r="50" fill="#ddd"/></svg>'
    )
    b64 = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


def _detect_mime(data: bytes | bytearray) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


def _is_valid_image(data: bytes | bytearray) -> bool:
    return data.startswith((b"\xff\xd8", b"\x89PNG\r\n\x1a\n", b"GIF8")) or (
        data.startswith(b"RIFF") and b"WEBP" in data[:16]
    )


class AvatarManager:
    def __init__(self, interface: Interface) -> None:
        self.reuse: ReusableAvatarManager = ReusableAvatarManager()
        self._interface = interface
        self._user_cache: dict[str, User] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_user(self, uid: str) -> User | None:
        if uid not in self._user_cache:
            try:
                user = await self._interface.get_user(uid)
                if user:
                    self._user_cache[uid] = user
            except Exception:
                return None
        return self._user_cache.get(uid)

    async def _get_avatar_url(self, uid: str) -> str | None:
        user = await self._get_user(uid)
        return user.avatar if user else None

    async def get_nickname(self, uid: str) -> str | None:
        user = await self._get_user(uid)
        return user and (user.nick or user.name or user.id)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0, follow_redirects=True)
        return self._client

    async def _get_avatar_data_uri(self, uid: str) -> str:
        """获取头像 URL，下载、校验并转为 base64 Data URI。

        失败时返回默认灰色头像兜底，但不写入缓存以便后续重试。
        """
        if not uid or uid == "0":
            return ""

        url = await self._get_avatar_url(uid)
        if not url:
            return ""

        if cached := await _avatar_cache.get(url):
            return cached

        async with _download_semaphore:
            try:
                async with self._get_client().stream("GET", url) as resp:
                    resp.raise_for_status()
                    ait = aiter(resp.aiter_bytes())
                    first_chunk = await anext(ait, None)
                    if first_chunk is None or not _is_valid_image(first_chunk):
                        logger.debug(f"头像数据无效 ({uid})")
                        return get_default_avatar_base64()

                    content = bytearray()
                    content.extend(first_chunk)
                    async for chunk in ait:
                        content.extend(chunk)

            except Exception as e:
                logger.debug(f"头像下载失败 ({uid}): {escape_tag(str(e))}")
                return get_default_avatar_base64()

        mime = _detect_mime(content)
        b64 = base64.b64encode(content).decode()
        uri = f"data:{mime};base64,{b64}"
        await _avatar_cache.set(url, value=uri, ttl=3 * 24 * 3600)
        return uri

    async def get_avatar(self, uid: str) -> tuple[str, str | None]:
        """获取头像 Data URI，失败时返回 None 以便使用默认头像。"""
        uri = await self._get_avatar_data_uri(uid)
        ref = self.reuse.register(uri, uid)
        return uri, ref
