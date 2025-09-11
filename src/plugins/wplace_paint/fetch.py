# ruff: noqa: N815
import base64
import functools
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal

import cloudscraper
from nonebot.utils import run_sync
from nonebot_plugin_htmlrender import get_browser
from playwright._impl._api_structures import SetCookieParam
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel, TypeAdapter

from .config import UserConfig
from .consts import FREE_COLORS, PAID_COLORS
from .utils import WplacePixelCoords, get_flag_emoji

WPLACE_ME_API_URL = "https://backend.wplace.live/me"
WPLACE_PURCHASE_API_URL = "https://backend.wplace.live/purchase"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
PW_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"


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


class RequestFailed(Exception):
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

    @property
    def coords(self) -> WplacePixelCoords:
        return WplacePixelCoords.from_lat_lon(self.latitude, self.longitude)


class FetchMeResponse(BaseModel):
    allianceId: int | None = None
    allianceRole: str | None = None
    charges: Charges
    country: str
    discord: str | None = None
    droplets: int
    equippedFlag: int  # 0 when not equipped
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

    def next_level_pixels(self) -> int:
        return math.ceil(
            math.pow(math.floor(self.level) * math.pow(30, 0.65), (1 / 0.65))
            - self.pixelsPainted
        )

    def format_target_droplets(self, target_droplets: int) -> str:
        droplets_needed = target_droplets - self.droplets
        pixels_to_paint = 0
        current_level = int(self.level)
        droplets_gained = 0

        while droplets_gained < droplets_needed:
            pixels_to_next_level = math.ceil(
                math.pow(current_level * math.pow(30, 0.65), (1 / 0.65))
            ) - (self.pixelsPainted + pixels_to_paint)

            # 如果仅靠绘制像素就能达到目标
            if droplets_gained + pixels_to_next_level >= droplets_needed:
                pixels_to_paint += droplets_needed - droplets_gained
                break

            # 升级
            pixels_to_paint += pixels_to_next_level
            droplets_gained += pixels_to_next_level + 500  # 绘制像素+升级奖励
            current_level += 1

        # 减去当前已有的像素
        net_pixels_needed = pixels_to_paint - self.charges.count
        total_seconds = max(0, net_pixels_needed) * self.charges.cooldownMs / 1000.0
        eta_time = datetime.now() + timedelta(seconds=total_seconds)

        return (
            f"[目标: 💧{target_droplets}] 还需 {pixels_to_paint} 像素\n"
            f"预计达成: {eta_time:%Y-%m-%d %H:%M}"
        )

    def format_notification(self, target_droplets: int | None = None) -> str:
        r = int(self.charges.remaining_secs())
        recover_time = datetime.now() + timedelta(seconds=r)
        flag = f" {get_flag_emoji(self.equippedFlag)}" if self.equippedFlag else ""
        base_msg = (
            f"{self.name} #{self.id}{flag} 💧{self.droplets}\n"
            f"Lv. {int(self.level)} (升级还需 {self.next_level_pixels()} 像素)\n"
            f"当前像素: {int(self.charges.count)}/{self.charges.max}\n"
            f"恢复耗时: {r // 3600}:{r // 60 % 60:02}:{r % 60:02}\n"
            f"预计回满: {recover_time:%Y-%m-%d %H:%M:%S}"
        )

        if target_droplets is None or target_droplets <= self.droplets:
            return base_msg
        extra_msg = self.format_target_droplets(target_droplets)
        return f"{base_msg}\n{extra_msg}"

    @functools.cached_property
    def own_flags(self) -> set[int]:
        b = base64.b64decode(self.flagsBitmap.encode("ascii"))
        return {i for i in range(len(b) * 8) if b[-(i // 8) - 1] & (1 << (i % 8))}

    @functools.cached_property
    def own_colors(self) -> set[str]:
        bitmap = self.extraColorsBitmap
        paid = {color for idx, color in enumerate(PAID_COLORS) if bitmap & (1 << idx)}
        return {"Transparent"} | set(FREE_COLORS) | paid


async def _fetch_with_playwright[T](
    url: str,
    validate: Callable[[str], T],
    cfg: UserConfig | None = None,
) -> T:
    browser = await get_browser()
    async with await browser.new_context(
        user_agent=USER_AGENT,
        viewport={"width": 1920, "height": 1080},
        java_script_enabled=True,
    ) as ctx:
        if cfg:
            await ctx.add_cookies(construct_pw_cookies(cfg.token, cfg.cf_clearance))
        await ctx.add_init_script(PW_INIT_SCRIPT)

        async with await ctx.new_page() as page:
            try:
                resp = await page.goto(url, wait_until="networkidle", timeout=20000)
            except PlaywrightTimeoutError as e:
                raise RequestFailed("Request timed out") from e
            if resp is None:
                raise RequestFailed("Failed to get response")
            if resp.status != 200:
                raise RequestFailed(f"Request failed with status code: {resp.status}")

            try:
                return validate(await resp.text())
            except Exception as e:
                raise RequestFailed("Failed to parse JSON response") from e


def _proxy_config() -> dict[str, str] | None:
    from .config import proxy

    return {"http": proxy, "https": proxy} if proxy is not None else None


_proxies = _proxy_config()


@run_sync
def _fetch_with_cloudscraper[T](
    url: str,
    validate: Callable[[str], T],
    cfg: UserConfig | None = None,
) -> T:
    cookies = cfg and construct_requests_cookies(cfg.token, cfg.cf_clearance)

    try:
        resp = cloudscraper.create_scraper().get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Sec-Ch-Ua": '"Chromium";v="140", '
                '"Not=A?Brand";v="24", "Google Chrome";v="140"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
            },
            cookies=cookies,
            proxies=_proxies,
            timeout=20,
        )
    except Exception as e:
        raise RequestFailed(f"Request failed: {e!r}") from e

    try:
        resp.raise_for_status()
    except Exception as e:
        raise RequestFailed(
            f"Request failed with status code: {resp.status_code}"
        ) from e

    try:
        return validate(resp.text)
    except Exception as e:
        raise RequestFailed("Failed to parse JSON response") from e


async def _fetch_with_auto_fallback[T](
    url: str,
    validate: Callable[[str], T],
    cfg: UserConfig | None = None,
) -> T:
    try:
        return await _fetch_with_cloudscraper(url, validate, cfg)
    except RequestFailed as e:
        from nonebot import logger

        logger.warning(f"cloudscraper failed ({e.msg}), trying playwright...")
        cs_exc = e

    try:
        return await _fetch_with_playwright(url, validate, cfg)
    except RequestFailed as e:
        pw_exc = e

    raise RequestFailed(
        f"Both methods failed: cloudscraper: {cs_exc.msg}; playwright: {pw_exc.msg}"
    ) from cs_exc


async def fetch_me(cfg: UserConfig) -> FetchMeResponse:
    resp = await _fetch_with_auto_fallback(
        WPLACE_ME_API_URL,
        FetchMeResponse.model_validate_json,
        cfg=cfg,
    )
    if resp.id != cfg.wp_user_id or resp.name != cfg.wp_user_name:
        cfg.wp_user_id = resp.id
        cfg.wp_user_name = resp.name
        cfg.save()
    return resp


@run_sync
def purchase(cfg: UserConfig, item_id: int, amount: int) -> None:
    try:
        resp = cloudscraper.create_scraper().post(
            WPLACE_PURCHASE_API_URL,
            headers={"User-Agent": USER_AGENT},
            cookies=construct_requests_cookies(cfg.token, cfg.cf_clearance),
            proxies=_proxies,
            json={"product": {"id": item_id, "amount": amount}},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        raise RequestFailed("Request failed") from e

    try:
        data = resp.json()
    except Exception as e:
        raise RequestFailed("Failed to parse JSON response") from e
    if not data["success"]:
        raise RequestFailed("Purchase failed: Unknown error")


PIXEL_INFO_URL = "https://backend.wplace.live/s0/pixel/{tlx}/{tly}?x={pxx}&y={pxy}"


class PixelPaintedBy(BaseModel):
    id: int
    name: str
    allianceId: int
    allianceName: str
    equippedFlag: int
    discord: str | None = None


class PixelRegion(BaseModel):
    id: int
    cityId: int
    name: str
    number: int
    countryId: int


class PixelInfo(BaseModel):
    paintedBy: PixelPaintedBy
    region: PixelRegion


async def get_pixel_info(coord: WplacePixelCoords) -> PixelInfo:
    url = PIXEL_INFO_URL.format(
        tlx=coord.tlx, tly=coord.tly, pxx=coord.pxx, pxy=coord.pxy
    )
    return await _fetch_with_auto_fallback(url, PixelInfo.model_validate_json)


class RankUser(BaseModel):
    id: int
    name: str
    allianceId: int
    allianceName: str
    pixelsPainted: int
    equippedFlag: int
    picture: str | None = None


type RankType = Literal["today", "week", "month", "all-time"]
RANK_URL = "https://backend.wplace.live/leaderboard/region/players/{}/{}"
_rank_resp_ta = TypeAdapter(list[RankUser])


async def fetch_region_rank(region_id: int, rank_type: RankType) -> list[RankUser]:
    return await _fetch_with_auto_fallback(
        RANK_URL.format(region_id, rank_type),
        _rank_resp_ta.validate_json,
    )
