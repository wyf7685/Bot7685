# ruff: noqa: S105

import base64
import contextlib
import hashlib
import io
import secrets
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import override
from urllib.parse import urlencode

import httpx
import PIL.Image
from pydantic import BaseModel

from src.service.cache import get_cache

from .common import Downloader
from .config import plugin_cofig
from .utils import generate_random_ascii_string

access_token_cache = get_cache("pixiv:access_token", str)

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

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(f"{OAUTH_BASE_URL}/auth/token", data=data)
        resp.raise_for_status()
        return OauthResult.model_validate(resp.json())


async def oauth_refresh(refresh_token: str) -> OauthResult:
    data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "include_policy": "true",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}) as client:
        resp = await client.post(f"{OAUTH_BASE_URL}/auth/token", data=data)
        resp.raise_for_status()
        return OauthResult.model_validate(resp.json())


_detail = {
    "illust": {
        "id": 144349015,
        "title": "I take some cookies for you",
        "type": "illust",
        "image_urls": {
            "square_medium": "https://i.pximg.net/c/540x540_10_webp/img-master/img/2026/05/04/15/52/16/144349015_p0_square1200.jpg",
            "medium": "https://i.pximg.net/c/540x540_70/img-master/img/2026/05/04/15/52/16/144349015_p0_master1200.jpg",
            "large": "https://i.pximg.net/c/600x1200_90_webp/img-master/img/2026/05/04/15/52/16/144349015_p0_master1200.jpg",
        },
        "caption": "3",
        "restrict": 0,
        "user": {
            "id": 105368797,
            "name": "DCmeC",
            "account": "user_eudc7788",
            "profile_image_urls": {
                "medium": "https://s.pximg.net/common/images/no_profile.png"
            },
            "is_followed": True,
            "is_accept_request": True,
        },
        "tags": [
            {"name": "Neuro-sama", "translated_name": None},
            {"name": "Evil-Neuro", "translated_name": None},
            {"name": "バーチャルYouTuber", "translated_name": None},
            {"name": "腋", "translated_name": None},
            {"name": "オフショルダー", "translated_name": None},
        ],
        "tools": [],
        "create_date": "2026-05-04T15:52:16+09:00",
        "page_count": 3,
        "width": 7607,
        "height": 5512,
        "sanity_level": 2,
        "x_restrict": 0,
        "series": None,
        "meta_single_page": {},
        "meta_pages": [
            {
                "image_urls": {
                    "square_medium": "https://i.pximg.net/c/360x360_10_webp/img-master/img/2026/05/04/15/52/16/144349015_p0_square1200.jpg",
                    "medium": "https://i.pximg.net/c/540x540_70/img-master/img/2026/05/04/15/52/16/144349015_p0_master1200.jpg",
                    "large": "https://i.pximg.net/c/600x1200_90_webp/img-master/img/2026/05/04/15/52/16/144349015_p0_master1200.jpg",
                    "original": "https://i.pximg.net/img-original/img/2026/05/04/15/52/16/144349015_p0.jpg",
                }
            },
            {
                "image_urls": {
                    "square_medium": "https://i.pximg.net/c/360x360_10_webp/img-master/img/2026/05/04/15/52/16/144349015_p1_square1200.jpg",
                    "medium": "https://i.pximg.net/c/540x540_70/img-master/img/2026/05/04/15/52/16/144349015_p1_master1200.jpg",
                    "large": "https://i.pximg.net/c/600x1200_90_webp/img-master/img/2026/05/04/15/52/16/144349015_p1_master1200.jpg",
                    "original": "https://i.pximg.net/img-original/img/2026/05/04/15/52/16/144349015_p1.jpg",
                }
            },
            {
                "image_urls": {
                    "square_medium": "https://i.pximg.net/c/360x360_10_webp/img-master/img/2026/05/04/15/52/16/144349015_p2_square1200.jpg",
                    "medium": "https://i.pximg.net/c/540x540_70/img-master/img/2026/05/04/15/52/16/144349015_p2_master1200.jpg",
                    "large": "https://i.pximg.net/c/600x1200_90_webp/img-master/img/2026/05/04/15/52/16/144349015_p2_master1200.jpg",
                    "original": "https://i.pximg.net/img-original/img/2026/05/04/15/52/16/144349015_p2.jpg",
                }
            },
        ],
        "total_view": 2836,
        "total_bookmarks": 451,
        "is_bookmarked": False,
        "visible": True,
        "is_muted": False,
        "seasonal_effect_animation_urls": None,
        "event_banners": None,
        "total_comments": 5,
        "illust_ai_type": 1,
        "illust_book_style": 0,
        "request": None,
        "comment_access_control": 0,
    }
}


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
    def __init__(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token
        self._headers = {
            "App-OS": "ios",
            "App-OS-Version": "12.2",
            "App-Version": "7.6.2",
            "User-Agent": "PixivIOSApp/7.6.2 (iOS 12.2; iPhone9,1)",
        }

    async def get_access_token(self) -> str:
        cache_key = hashlib.sha256(self.refresh_token.encode()).hexdigest()
        if cached_token := await access_token_cache.get(cache_key):
            return cached_token

        headers = {"User-Agent": "PixivAndroidApp/6.66.1 (Android 11; Pixel 5)"}
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "include_policy": "true",
            "refresh_token": self.refresh_token,
        }

        async with httpx.AsyncClient(headers=headers) as client:
            resp = await client.post(f"{OAUTH_BASE_URL}/auth/token", data=data)
            resp.raise_for_status()
            oauth_result = OauthResult.model_validate(resp.json())

        await access_token_cache.set(
            cache_key,
            oauth_result.access_token,
            ttl=oauth_result.expires_in - 60,
        )
        return oauth_result.access_token

    async def get_headers(self) -> dict[str, str]:
        access_token = await self.get_access_token()
        headers = self._headers.copy()
        headers["Authorization"] = f"Bearer {access_token}"
        return headers

    async def get_illust_detail(self, illust_id: int) -> IllustDetail:
        url = f"{APP_BASE_URL}/v1/illust/detail"
        params = {"illust_id": illust_id}
        headers = await self.get_headers()

        async with httpx.AsyncClient(headers=headers) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return IllustDetail.model_validate(resp.json())

    async def download_image(
        self,
        url: str,
        client: httpx.AsyncClient | None = None,
    ) -> bytes:
        headers = {
            "Referer": "https://www.pixiv.net/",
            "User-Agent": "PixivIOSApp/7.6.2 (iOS 12.2; iPhone9,1)",
        }
        cm = contextlib.nullcontext(client) if client else httpx.AsyncClient()
        async with cm as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.content


class PixivDownloader(Downloader[Illust, str]):
    def __init__(self) -> None:
        if plugin_cofig.pixiv_refresh_token is None:
            raise RuntimeError("Pixiv refresh token not configured")

        refresh_token = plugin_cofig.pixiv_refresh_token.get_secret_value()
        self.pixiv_client = PixivClient(refresh_token)

    @override
    def create_httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient()

    @override
    async def fetch_index(self, pid: int) -> Illust:
        return (await self.pixiv_client.get_illust_detail(pid)).illust

    @override
    async def format_summary(self, illust: Illust) -> str:
        return (
            f"ID: {illust.id}\n"
            f"标题: {illust.title}\n"
            f"作者: {illust.user.name}\n"
            f"标签: {', '.join(tag.name for tag in illust.tags)}\n"
            f"页数: {illust.page_count}"
        )

    @override
    async def generate_task(self, illust: Illust) -> AsyncGenerator[tuple[str, str]]:
        for idx, page in enumerate(illust.meta_pages, start=1):
            if url := page.image_urls.get():
                yield f"P_{idx}", url

    @override
    async def execute_task(self, url: str) -> bytes:
        raw = await self.pixiv_client.download_image(url, await self.get_httpx_client())
        im = PIL.Image.open(io.BytesIO(raw)).convert("RGB")
        im.info["comment"] = generate_random_ascii_string(16)
        with io.BytesIO() as output:
            im.save(output, format="JPEG")
            return output.getvalue()
