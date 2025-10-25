import hashlib
from collections.abc import Callable

import cloudscraper
from nonebot import logger
from nonebot.utils import flatten_exception_group, run_sync
from nonebot_plugin_htmlrender import get_browser
from playwright._impl._api_structures import SetCookieParam
from playwright._impl._errors import TimeoutError as PlaywrightTimeoutError
from pydantic import TypeAdapter

from src.utils import with_semaphore

from .config import UserConfig
from .pawtect import pawtect_sign
from .schemas import FetchMeResponse, PixelInfo, PurchaseItem, RankType, RankUser
from .utils import WplacePixelCoords, with_retry

WPLACE_ME_API_URL = "https://backend.wplace.live/me"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)
PW_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"

type ValidateFunc[T] = Callable[[str | bytes], T]


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
    status_code: int | None = None

    def __init__(self, msg: str, status_code: int | None = None) -> None:
        super().__init__(msg)
        self.msg = msg
        self.status_code = status_code


def extract_first_status_code(*exc_groups: ExceptionGroup[RequestFailed]) -> int | None:
    for exc_group in exc_groups:
        for e in flatten_exception_group(exc_group):
            if e.status_code is not None:
                return e.status_code
    return None


def flatten_request_failed_msg(exc_group: ExceptionGroup[RequestFailed]) -> str:
    return "\n".join(e.msg for e in flatten_exception_group(exc_group))


async def _fetch_with_playwright[T](
    url: str,
    validate: ValidateFunc[T],
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
            except Exception as e:
                raise RequestFailed(f"Request failed: {e!r}") from e

            if resp is None:
                raise RequestFailed("Failed to get response")
            if resp.status != 200:
                raise RequestFailed(
                    f"Request failed with status code: {resp.status}",
                    status_code=resp.status,
                )

            try:
                return validate(await resp.text())
            except Exception as e:
                raise RequestFailed("Failed to parse JSON response") from e


def _proxy_config() -> dict[str, str] | None:
    from .config import proxy

    return {"http": proxy, "https": proxy} if proxy is not None else None


_proxies = _proxy_config()
_scraper_headers = {
    "User-Agent": USER_AGENT,
    "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Origin": "https://wplace.live",
}


class TooManyRequests(RequestFailed): ...


class InvalidCredentials(RequestFailed): ...


@with_semaphore(8)
@with_retry(TooManyRequests, InvalidCredentials, retries=3, delay=1)
@run_sync
def _fetch_with_cloudscraper[T](
    url: str,
    validate: ValidateFunc[T],
    cfg: UserConfig | None = None,
) -> T:
    try:
        resp = cloudscraper.create_scraper().get(
            url,
            headers=_scraper_headers,
            cookies=cfg and construct_requests_cookies(cfg.token, cfg.cf_clearance),
            proxies=_proxies,
            timeout=20,
        )
    except Exception as e:
        raise RequestFailed(f"Request failed: {e!r}") from e

    try:
        resp.raise_for_status()
    except Exception as e:
        if resp.status_code == 429:  # Too Many Requests
            raise TooManyRequests("Got status code: 429", 429) from e
        if resp.status_code in {401, 500}:
            raise InvalidCredentials(
                f"Request failed with status code: {resp.status_code}",
                status_code=resp.status_code,
            ) from e

        raise RequestFailed(
            f"Request failed with status code: {resp.status_code}",
            status_code=resp.status_code,
        ) from e

    try:
        return validate(resp.content)
    except Exception as e:
        raise RequestFailed("Failed to parse JSON response") from e


async def _fetch_with_auto_fallback[T](
    url: str,
    validate: ValidateFunc[T],
    cfg: UserConfig | None = None,
) -> T:
    try:
        return await _fetch_with_cloudscraper(url, validate, cfg)
    except* RequestFailed as exc_group:
        if any(e.status_code in {401, 500} for e in flatten_exception_group(exc_group)):
            logger.warning("cloudscraper got status code 401/500, not falling back")
            raise

        logger.warning(f"cloudscraper failed ({exc_group!r}), trying playwright...")
        cs_exc = exc_group

    try:
        return await _fetch_with_playwright(url, validate, cfg)
    except RequestFailed as exc:
        logger.warning(f"playwright also failed ({exc!r})")
        pw_exc = exc

    raise ExceptionGroup(
        "Both cloudscraper and playwright requests failed",
        [*flatten_exception_group(cs_exc), pw_exc],
    )


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


WPLACE_PURCHASE_API_URL = "https://backend.wplace.live/purchase"


@run_sync
def purchase(cfg: UserConfig, item: PurchaseItem, amount: int) -> None:
    try:
        resp = cloudscraper.create_scraper().post(
            WPLACE_PURCHASE_API_URL,
            headers={"User-Agent": USER_AGENT},
            cookies=construct_requests_cookies(cfg.token, cfg.cf_clearance),
            proxies=_proxies,
            json={"product": {"id": item.value, "amount": amount}},
            timeout=20,
        )
        resp.raise_for_status()
    except Exception as e:
        raise RequestFailed(f"Request failed: {e!r}") from e

    try:
        data = resp.json()
    except Exception as e:
        raise RequestFailed("Failed to parse JSON response") from e
    if not data["success"]:
        raise RequestFailed("Purchase failed: Unknown error")


PIXEL_INFO_URL = "https://backend.wplace.live/s0/pixel/{coord.tlx}/{coord.tly}?x={coord.pxx}&y={coord.pxy}"


async def get_pixel_info(coord: WplacePixelCoords) -> PixelInfo:
    return await _fetch_with_auto_fallback(
        PIXEL_INFO_URL.format(coord=coord),
        PixelInfo.model_validate_json,
    )


RANK_URL = "https://backend.wplace.live/leaderboard/region/players/{}/{}"
_rank_resp_ta = TypeAdapter(list[RankUser])


async def fetch_region_rank(region_id: int, rank_type: RankType) -> list[RankUser]:
    return await _fetch_with_auto_fallback(
        RANK_URL.format(region_id, rank_type),
        _rank_resp_ta.validate_json,
    )


PAINT_URL = "https://backend.wplace.live/s0/pixel/{}/{}"


@run_sync
def post_paint_pixels(
    cfg: UserConfig,
    tile: tuple[int, int],
    pixels: list[tuple[tuple[int, int], int]],
) -> int:
    colors, coords = [], []
    for pixel, color_id in pixels:
        colors.append(color_id)
        coords.extend(pixel)
    payload = {
        "colors": colors,
        "coords": coords,
        "fp": hashlib.sha256(str(cfg.wp_user_id).encode()).hexdigest()[:32],
    }
    pawtect_token = pawtect_sign(payload)

    url = PAINT_URL.format(*tile)
    headers = {
        "x-pawtect-token": pawtect_token,
        "x-pawtect-variant": "koala",
        "referrer": "https://wplace.live/",
    }

    try:
        resp = cloudscraper.create_scraper().post(
            url,
            headers=headers,
            cookies=construct_requests_cookies(cfg.token, cfg.cf_clearance),
            json=payload,
            proxies=_proxies,
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise RequestFailed(f"Paint request failed: {e!r}") from e

    return data["painted"]
