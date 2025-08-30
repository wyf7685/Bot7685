# ruff: noqa: N815
import functools
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

from nonebot.utils import run_sync
from nonebot_plugin_htmlrender import get_browser
from playwright._impl._api_structures import SetCookieParam
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

from .config import ConfigModel

WPLACE_ME_API_URL = "https://backend.wplace.live/me"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/138.0.0.0 Safari/537.36"
)
PW_PAGE_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


def construct_requests_cookies(token: str, cf_clearance: str) -> dict[str, str]:
    return {"j": token, "cf_clearance": cf_clearance}


def construct_pw_cookies(token: str, cf_clearance: str) -> list[SetCookieParam]:
    return [
        {
            "name": "j",
            "value": token,
            "domain": "backend.wplace.live",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "Lax",
        },
        {
            "name": "cf_clearance",
            "value": cf_clearance,
            "domain": "backend.wplace.live",
            "path": "/",
            "httpOnly": False,
            "secure": True,
            "sameSite": "None",
        },
    ]


class FetchFailed(Exception):
    msg: str

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


class Charges(BaseModel):
    cooldownMs: int
    count: float
    max: int

    def remaining_secs(self) -> float:
        return (self.max - self.count) * (self.cooldownMs / 1000.0)


class FavoriteLocation(BaseModel):
    id: int
    name: str = ""
    latitude: float
    longitude: float


class FetchMeResponse(BaseModel):
    allianceId: int | None = None
    allianceRole: str | None = None
    charges: Charges
    country: str
    discord: str | None = None
    droplets: int
    equippedFlag: int
    extraColorsBitmap: int
    favoriteLocations: list[FavoriteLocation]
    flagsBitmap: str
    id: int
    isCustomer: bool
    level: float
    maxFavoriteLocations: int
    name: str
    needsPhoneVerification: bool
    picture: str
    pixelsPainted: int
    showLastPixel: bool

    def format_notification(self) -> str:
        r = int(self.charges.remaining_secs())
        recover_time = datetime.now() + timedelta(seconds=r)
        return (
            f"用户: {self.name} (ID: {self.id})\n"
            f"当前像素: {int(self.charges.count)}/{self.charges.max}\n"
            f"恢复耗时: {r // 3600}:{r // 60 % 60:02}:{r % 60:02}\n"
            f"预计回满: {recover_time:%Y-%m-%d %H:%M:%S}"
        )


type FetchFn = Callable[[ConfigModel], Awaitable[FetchMeResponse]]


def _save_user_info(fn: FetchFn) -> FetchFn:
    @functools.wraps(fn)
    async def wrapper(cfg: ConfigModel) -> FetchMeResponse:
        resp = await fn(cfg)
        cfg.wp_user_id = resp.id
        cfg.wp_user_name = resp.name
        cfg.save()
        return resp

    return wrapper


@_save_user_info
async def fetch_me_with_async_playwright(cfg: ConfigModel) -> FetchMeResponse:
    async with await (await get_browser()).new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        java_script_enabled=True,
    ) as ctx:
        await ctx.add_cookies(construct_pw_cookies(cfg.token, cfg.cf_clearance))
        async with await ctx.new_page() as page:
            await page.add_init_script(PW_PAGE_SCRIPT)
            try:
                resp = await page.goto(
                    WPLACE_ME_API_URL,
                    wait_until="networkidle",
                    timeout=20000,
                )
            except PlaywrightTimeoutError as e:
                raise FetchFailed("Request timed out") from e
            if resp is None:
                raise FetchFailed("Failed to get response")
            if resp.status != 200:
                raise FetchFailed(f"Request failed with status code: {resp.status}")

            try:
                return FetchMeResponse.model_validate_json(await resp.text())
            except Exception as e:
                raise FetchFailed("Failed to parse JSON response") from e


@_save_user_info
@run_sync
def fetch_me_with_cloudscraper(cfg: ConfigModel) -> FetchMeResponse:
    import cloudscraper

    scraper = cloudscraper.create_scraper()
    try:
        resp = scraper.get(
            WPLACE_ME_API_URL,
            headers={"User-Agent": USER_AGENT},
            cookies=construct_requests_cookies(cfg.token, cfg.cf_clearance),
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        raise FetchFailed("Request failed") from e

    try:
        return FetchMeResponse.model_validate_json(resp.text)
    except Exception as e:
        raise FetchFailed("Failed to parse JSON response") from e


# async def fetch_me(cfg: ConfigModel) -> FetchMeResponse:
#     try:
#         return await fetch_me_with_cloudscraper(cfg)
#     except FetchFailed as e:
#         from nonebot import logger

#         logger.warning(f"cloudscraper fetch failed ({e!r}), trying playwright...")

#     return await fetch_me_with_async_playwright(cfg)


fetch_me = fetch_me_with_async_playwright
