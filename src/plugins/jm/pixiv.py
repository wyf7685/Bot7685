# ruff: noqa: S105

import asyncio
import base64
import contextlib
import hashlib
import io
import os
import secrets
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import override
from urllib.parse import urlencode

import anyio
import httpx2
import PIL.Image
from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel

from .common import Downloader
from .utils import generate_random_ascii_string

TOKEN_FILE = get_plugin_data_file("pixiv_refresh_token")

# https://gist.github.com/ZipFile/c9ebedb224406f4f11845ab700124362
# Latest app version can be found using GET /v1/application-info/android
USER_AGENT = "PixivAndroidApp/6.66.1 (Android 11; Pixel 5)"
APP_BASE_URL = "https://app-api.pixiv.net"
OAUTH_BASE_URL = "https://oauth.secure.pixiv.net"
CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"


def oauth_pkce() -> tuple[str, str]:
    """Proof Key for Code Exchange by OAuth Public Clients (RFC7636)."""

    code_verifier = secrets.token_urlsafe(32)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )

    return code_verifier, code_challenge


def construct_login_url() -> tuple[str, str]:
    code_verifier, code_challenge = oauth_pkce()
    login_params = {
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "client": "pixiv-android",
    }

    return f"{APP_BASE_URL}/web/v1/login?{urlencode(login_params)}", code_verifier


class OauthResult(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int


async def oauth_login(code: str, code_verifier: str) -> OauthResult:
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "code_verifier": code_verifier,
        "grant_type": "authorization_code",
        "include_policy": "true",
        "redirect_uri": f"{APP_BASE_URL}/web/v1/users/auth/pixiv/callback",
    }

    async with httpx2.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(f"{OAUTH_BASE_URL}/auth/token", data=data)
        resp.raise_for_status()
        return OauthResult.model_validate_json(resp.content)


async def oauth_refresh(refresh_token: str) -> OauthResult:
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "include_policy": "true",
        "refresh_token": refresh_token,
    }

    async with httpx2.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(f"{OAUTH_BASE_URL}/auth/token", data=data)
        resp.raise_for_status()
        return OauthResult.model_validate_json(resp.content)


class PixivAuth:
    def __init__(self) -> None:
        self._refresh_token: str | None = None
        self._access_token: str | None = None
        self._expires_at: datetime | None = None
        self._lock = asyncio.Lock()

    def _schedule(self, delay: int) -> None:
        scheduler.add_job(
            self.scheduled_refresh,
            "date",
            run_date=datetime.now(UTC) + timedelta(seconds=delay),
            id="jm_pixiv_refresh",
            replace_existing=True,
            misfire_grace_time=None,
            max_instances=1,
        )

    @staticmethod
    def _write_token(token: str) -> None:
        temporary = TOKEN_FILE.with_name(
            f".{TOKEN_FILE.name}.{secrets.token_hex(8)}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                stream.write(token)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                temporary.chmod(0o600)
            temporary.replace(TOKEN_FILE)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    async def _accept(self, result: OauthResult) -> None:
        await anyio.to_thread.run_sync(self._write_token, result.refresh_token)
        self._refresh_token = result.refresh_token
        self._access_token = result.access_token
        self._expires_at = datetime.now(UTC) + timedelta(seconds=result.expires_in)
        self._schedule(max(1, result.expires_in - 60))

    async def startup(self) -> None:
        try:
            self._refresh_token = await anyio.to_thread.run_sync(
                lambda: (
                    TOKEN_FILE.read_text(encoding="utf-8").strip()
                    if TOKEN_FILE.exists()
                    else None
                )
            )
        except OSError as exc:
            logger.error(f"读取 Pixiv 凭据失败: {type(exc).__name__}")
            return
        if self._refresh_token:
            self._schedule(0)

    async def login(self, code: str, code_verifier: str) -> None:
        async with self._lock:
            await self._accept(await oauth_login(code, code_verifier))

    async def refresh(self, *, force: bool = False) -> str:
        async with self._lock:
            if (
                not force
                and self._access_token
                and self._expires_at
                and datetime.now(UTC) < self._expires_at
            ):
                return self._access_token
            if not self._refresh_token:
                raise RuntimeError("Pixiv 尚未登录，请由超级用户私聊执行 pixivlogin")
            try:
                result = await oauth_refresh(self._refresh_token)
                await self._accept(result)
            except Exception:
                self._schedule(300)
                raise
            return result.access_token

    async def scheduled_refresh(self) -> None:
        try:
            await self.refresh(force=True)
        except Exception as exc:
            logger.error(f"刷新 Pixiv 凭据失败: {type(exc).__name__}")


pixiv_auth = PixivAuth()
get_driver().on_startup(pixiv_auth.startup)


class ImageUrls(BaseModel):
    square_medium: str | None = None
    medium: str | None = None
    large: str | None = None
    original: str | None = None

    def get(self) -> str | None:
        return self.original or self.large or self.medium or self.square_medium


class User(BaseModel):
    id: int
    name: str
    account: str
    profile_image_urls: ImageUrls
    is_followed: bool
    is_accept_request: bool


class Tag(BaseModel):
    name: str
    translated_name: str | None = None


class MetaPage(BaseModel):
    image_urls: ImageUrls


class Illust(BaseModel):
    id: int
    title: str
    image_urls: ImageUrls
    caption: str
    restrict: int
    user: User
    tags: list[Tag]
    create_date: datetime
    page_count: int
    width: int
    height: int
    sanity_level: int
    x_restrict: int
    meta_pages: list[MetaPage]


class IllustDetail(BaseModel):
    illust: Illust


class PixivClient:
    def __init__(self) -> None:
        self._headers = {
            "App-OS": "ios",
            "App-OS-Version": "12.2",
            "App-Version": "7.6.2",
            "User-Agent": "PixivIOSApp/7.6.2 (iOS 12.2; iPhone9,1)",
        }

    async def get_headers(self) -> dict[str, str]:
        access_token = await pixiv_auth.refresh()
        headers = self._headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        return headers

    async def get_illust_detail(self, illust_id: int) -> IllustDetail:
        url = f"{APP_BASE_URL}/v1/illust/detail"
        params = {"illust_id": illust_id}
        headers = await self.get_headers()

        async with httpx2.AsyncClient(headers=headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return IllustDetail.model_validate_json(resp.content)

    async def download_image(
        self,
        url: str,
        client: httpx2.AsyncClient | None = None,
    ) -> bytes:
        headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": "PixivIOSApp/7.6.2 (iOS 12.2; iPhone9,1)",
        }
        cm = contextlib.nullcontext(client) if client else httpx2.AsyncClient()
        async with cm as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content


class PixivDownloader(Downloader[Illust, str]):
    def __init__(self) -> None:
        self.pixiv_client = PixivClient()

    @override
    def create_client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient()

    @override
    async def fetch_index(self, pid: int) -> Illust:
        return (await self.pixiv_client.get_illust_detail(pid)).illust

    @override
    async def format_summary(self, illust: Illust) -> str:
        return (
            f"ID: {illust.id}\n"
            f"标题: {illust.title}\n"
            f"作者: {illust.user.name}\n"
            f"标签: {", ".join(tag.name for tag in illust.tags)}\n"
            f"页数: {illust.page_count}"
        )

    @override
    async def generate_task(self, illust: Illust) -> AsyncGenerator[tuple[str, str]]:
        for idx, page in enumerate(illust.meta_pages, start=1):
            if url := page.image_urls.get():
                yield f"P_{idx}", url

    @override
    async def execute_task(self, url: str) -> bytes:
        raw = await self.pixiv_client.download_image(url, await self.get_client())
        im = PIL.Image.open(io.BytesIO(raw)).convert("RGB")
        im.info["comment"] = generate_random_ascii_string(16)
        with io.BytesIO() as output:
            im.save(output, format="JPEG")
            return output.getvalue()
