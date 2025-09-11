import functools
import math
import re
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass
from typing import NamedTuple

import anyio
from loguru import logger

from .consts import ALL_COLORS, FLAG_MAP


class WplaceAbsCoords(NamedTuple):
    x: int
    y: int

    def offset(self, dx: int, dy: int) -> "WplaceAbsCoords":
        return WplaceAbsCoords(self.x + dx, self.y + dy)

    def to_pixel(self) -> "WplacePixelCoords":
        tlx, pxx = divmod(self.x, 1000)
        tly, pxy = divmod(self.y, 1000)
        return WplacePixelCoords(tlx, tly, pxx, pxy)


BLUE_MARBLE_COORDS_PATTERN = re.compile(
    r".+?Tl X: (\d+), Tl Y: (\d+), Px X: (\d+), Px Y: (\d+).+?"
)


@dataclass
class WplacePixelCoords:
    # each tile contains 1000x1000 pixels, from 0 to 999
    tlx: int  # tile X
    tly: int  # tile Y
    pxx: int  # pixel X
    pxy: int  # pixel Y

    # Blue Marble 格式
    # f"Tl X: {self.tlx}, Tl Y: {self.tly}, Px X: {self.pxx}, Px Y: {self.pxy}"

    def human_repr(self) -> str:
        return f"({self.tlx}, {self.tly}) + ({self.pxx}, {self.pxy})"

    def to_abs(self) -> WplaceAbsCoords:
        return WplaceAbsCoords(self.tlx * 1000 + self.pxx, self.tly * 1000 + self.pxy)

    def offset(self, dx: int, dy: int) -> "WplacePixelCoords":
        return self.to_abs().offset(dx, dy).to_pixel()

    def to_share_url(self) -> str:
        lat, lon = pixel_to_latlon(self)
        return f"https://wplace.live/?lat={lat}&lng={lon}&zoom=20"

    @classmethod
    def from_lat_lon(cls, lat: float, lon: float) -> "WplacePixelCoords":
        return latlon_to_pixel(LatLon(lat, lon))

    @classmethod
    def parse(cls, s: str) -> "WplacePixelCoords":
        if not (m := BLUE_MARBLE_COORDS_PATTERN.match(s)):
            raise ValueError(f"Invalid coords: {s}")
        return cls(int(m[1]), int(m[2]), int(m[3]), int(m[4]))


class LatLon(NamedTuple):
    lat: float
    lon: float


def fix_coords(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> tuple[WplacePixelCoords, WplacePixelCoords]:
    x1, y1 = coord1.to_abs()
    x2, y2 = coord2.to_abs()
    (x1, x2), (y1, y2) = sorted((x1, x2)), sorted((y1, y2))
    return WplaceAbsCoords(x1, y1).to_pixel(), WplaceAbsCoords(x2, y2).to_pixel()


def get_all_tile_coords(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> Iterable[tuple[int, int]]:
    coord1, coord2 = fix_coords(coord1, coord2)
    yield from (
        (x, y)
        for x in range(coord1.tlx, coord2.tlx + 1)
        for y in range(coord1.tly, coord2.tly + 1)
    )


def get_size(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> tuple[int, int]:
    coord1, coord2 = fix_coords(coord1, coord2)
    x1, y1 = coord1.to_abs()
    x2, y2 = coord2.to_abs()
    return x2 - x1 + 1, y2 - y1 + 1


# 从多点校准中提取的常量参数
SCALE_X = 325949.3234522017
SCALE_Y = -325949.3234522014
OFFSET_X = 1023999.5
OFFSET_Y = 1023999.4999999999


def pixel_to_latlon(pixel: WplacePixelCoords) -> LatLon:
    """将像素坐标转换为经纬度 (使用墨卡托投影)"""
    abs_coords = pixel.to_abs()

    # 从像素坐标计算墨卡托坐标
    merc_x = (abs_coords.x - OFFSET_X) / SCALE_X
    merc_y = (abs_coords.y - OFFSET_Y) / SCALE_Y

    # 从墨卡托坐标计算经纬度
    lon = math.degrees(merc_x)
    lat = math.degrees(2 * math.atan(math.exp(merc_y)) - math.pi / 2)

    return LatLon(lat, lon)


def latlon_to_pixel(latlon: LatLon) -> WplacePixelCoords:
    """将经纬度转换为像素坐标 (使用墨卡托投影)"""
    # 计算墨卡托坐标
    merc_x = math.radians(latlon.lon)
    merc_y = math.log(math.tan(math.pi / 4 + math.radians(latlon.lat) / 2))

    # 计算像素绝对坐标
    abs_x = int(merc_x * SCALE_X + OFFSET_X)
    abs_y = int(merc_y * SCALE_Y + OFFSET_Y)

    return WplaceAbsCoords(abs_x, abs_y).to_pixel()


def get_flag_emoji(id: int) -> str:
    return FLAG_MAP.get(id, "")


def find_color_name(rgba: tuple[int, int, int, int]) -> str:
    if rgba[3] == 0:
        return "Transparent"

    rgb = rgba[:3]
    for name, value in ALL_COLORS.items():
        if value == rgb:
            return name

    # not found, find the closest one
    def color_distance(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> int:
        return sum((a - b) ** 2 for a, b in zip(c1, c2, strict=True))

    closest_name = ""
    closest_distance = float("inf")
    for name, value in ALL_COLORS.items():
        dist = color_distance(rgb, value)
        if dist < closest_distance:
            closest_distance = dist
            closest_name = name
    return closest_name


def normalize_color_name(name: str) -> str | None:
    if name == "Transparent":
        return name

    name = name.strip().lower().replace(" ", "_")
    for color_name in ALL_COLORS:
        if color_name.lower().replace(" ", "_") == name:
            return color_name

    return None


def parse_rgb_str(s: str) -> tuple[int, int, int] | None:
    if not (s := s.removeprefix("#").lower()) or len(s) != 6:
        return None

    if any(c not in "0123456789abcdef" for c in s):
        return None

    return tuple(int(s[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore


type AsyncCallable[**P, R] = Callable[P, Coroutine[None, None, R]]


def with_retry[**P, R](
    *exc: type[BaseException],
    retries: int = 3,
    delay: float = 0,
) -> Callable[[AsyncCallable[P, R]], AsyncCallable[P, R]]:
    assert retries >= 1
    if not exc:
        exc_types = Exception
    elif len(exc) == 1:
        exc_types = exc[0]
    else:
        exc_types = tuple(exc)

    def decorator(func: AsyncCallable[P, R]) -> AsyncCallable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: BaseException | None = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except exc_types as e:
                    logger.debug(
                        f"函数 {func.__name__} "
                        f"第 {attempt + 1}/{retries} 次调用失败: {e!r}"
                    )
                    last_exc = e
                    if delay > 0:
                        await anyio.sleep(delay)

            assert isinstance(last_exc, BaseException)
            raise last_exc

        return wrapper

    return decorator
