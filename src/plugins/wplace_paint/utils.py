import functools
import math
import re
import time
import types
from collections.abc import Callable, Coroutine, Iterable, Sequence
from dataclasses import dataclass
from typing import NamedTuple, Self

import anyio
from loguru import logger

from .consts import ALL_COLORS, FLAG_MAP

# 从多点校准中提取的常量参数
SCALE_X = 325949.3234522017
SCALE_Y = -325949.3234522014
OFFSET_X = 1023999.5
OFFSET_Y = 1023999.4999999999

WPLACE_TILE_SIZE = 1000  # 每个 tile 包含 1000x1000 像素


class WplaceAbsCoords(NamedTuple):
    x: int
    y: int

    def offset(self, dx: int, dy: int) -> "WplaceAbsCoords":
        return WplaceAbsCoords(self.x + dx, self.y + dy)

    def to_pixel(self) -> "WplacePixelCoords":
        tlx, pxx = divmod(self.x, WPLACE_TILE_SIZE)
        tly, pxy = divmod(self.y, WPLACE_TILE_SIZE)
        return WplacePixelCoords(tlx, tly, pxx, pxy)


class LatLon(NamedTuple):
    lat: float
    lon: float

    def to_pixel(self) -> "WplacePixelCoords":
        return WplacePixelCoords.from_lat_lon(self.lat, self.lon)


# Blue Marble 格式
# f"Tl X: {self.tlx}, Tl Y: {self.tly}, Px X: {self.pxx}, Px Y: {self.pxy}"
BLUE_MARBLE_COORDS_PATTERN = re.compile(
    r".*Tl X: (\d+), Tl Y: (\d+), Px X: (\d+), Px Y: (\d+).*"
)


@dataclass
class WplacePixelCoords:
    # each tile contains 1000x1000 pixels, from 0 to 999
    tlx: int  # tile X
    tly: int  # tile Y
    pxx: int  # pixel X
    pxy: int  # pixel Y

    def human_repr(self) -> str:
        return f"({self.tlx}, {self.tly}) + ({self.pxx}, {self.pxy})"

    def to_abs(self) -> WplaceAbsCoords:
        return WplaceAbsCoords(
            self.tlx * WPLACE_TILE_SIZE + self.pxx,
            self.tly * WPLACE_TILE_SIZE + self.pxy,
        )

    def offset(self, dx: int, dy: int) -> "WplacePixelCoords":
        return self.to_abs().offset(dx, dy).to_pixel()

    def to_lat_lon(self) -> LatLon:
        x, y = self.to_abs()

        # 从像素坐标计算墨卡托坐标
        merc_x = (x - OFFSET_X) / SCALE_X
        merc_y = (y - OFFSET_Y) / SCALE_Y

        # 从墨卡托坐标计算经纬度
        lon = math.degrees(merc_x)
        lat = math.degrees(2 * math.atan(math.exp(merc_y)) - math.pi / 2)

        return LatLon(lat, lon)

    def to_share_url(self) -> str:
        lat, lon = self.to_lat_lon()
        return f"https://wplace.live/?lat={lat}&lng={lon}&zoom=20"

    @classmethod
    def from_lat_lon(cls, lat: float, lon: float) -> "WplacePixelCoords":
        # 计算墨卡托坐标
        merc_x = math.radians(lon)
        merc_y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

        # 计算像素绝对坐标
        abs_x = int(merc_x * SCALE_X + OFFSET_X)
        abs_y = int(merc_y * SCALE_Y + OFFSET_Y)

        return WplaceAbsCoords(abs_x, abs_y).to_pixel()

    @classmethod
    def parse(cls, s: str) -> Self:
        if not (m := BLUE_MARBLE_COORDS_PATTERN.match(s)):
            raise ValueError(f"Invalid coords: {s}")
        return cls(int(m[1]), int(m[2]), int(m[3]), int(m[4]))

    def fix_with(
        self, other: "WplacePixelCoords"
    ) -> tuple["WplacePixelCoords", "WplacePixelCoords"]:
        (x1, y1), (x2, y2) = self.to_abs(), other.to_abs()
        (x1, x2), (y1, y2) = sorted((x1, x2)), sorted((y1, y2))
        return WplaceAbsCoords(x1, y1).to_pixel(), WplaceAbsCoords(x2, y2).to_pixel()

    def all_tile_coords(self, other: "WplacePixelCoords") -> Iterable[tuple[int, int]]:
        coord1, coord2 = self.fix_with(other)
        yield from (
            (x, y)
            for x in range(coord1.tlx, coord2.tlx + 1)
            for y in range(coord1.tly, coord2.tly + 1)
        )

    def size_with(self, other: "WplacePixelCoords") -> tuple[int, int]:
        coord1, coord2 = self.fix_with(other)
        (x1, y1), (x2, y2) = coord1.to_abs(), coord2.to_abs()
        return x2 - x1 + 1, y2 - y1 + 1


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


_NORMALIZED_COLOR_NAMES: dict[str, str] = {
    name.lower().replace(" ", "_"): name for name in ALL_COLORS
}


def normalize_color_name(name: str) -> str | None:
    if name == "Transparent":
        return name

    name = name.strip().lower().replace(" ", "_")
    return _NORMALIZED_COLOR_NAMES.get(name)


def parse_color_names(names: Sequence[str]) -> Sequence[str]:
    result: list[str] = []
    idx = 0
    while idx < len(names):
        for length in range(2, -1, -1):
            if idx + length >= len(names):
                continue
            name = "_".join(names[idx : idx + length + 1]).lower().strip()
            if (color_name := _NORMALIZED_COLOR_NAMES.get(name)) is not None:
                result.append(color_name)
                idx += length + 1
                break
        else:
            idx += 1
    return result


def parse_rgb_str(s: str) -> tuple[int, int, int] | None:
    if not (s := s.removeprefix("#").lower()) or len(s) != 6:
        return None

    if any(c not in "0123456789abcdef" for c in s):
        return None

    r, g, b = (int(s[i : i + 2], 16) for i in (0, 2, 4))
    return r, g, b


type AsyncCallable[**P, R] = Callable[P, Coroutine[None, None, R]]


def with_retry[**P, R](
    *exc: type[Exception],
    retries: int = 3,
    delay: float = 0,
) -> Callable[[AsyncCallable[P, R]], AsyncCallable[P, R]]:
    assert retries >= 1, "retries must be at least 1"
    assert delay >= 0, "delay must be non-negative"

    if not exc:
        exc_types = Exception
    elif len(exc) == 1:
        exc_types = exc[0]
    else:
        exc_types = (*exc,)

    def decorator(func: AsyncCallable[P, R]) -> AsyncCallable[P, R]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            caught: list[Exception] = []

            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except exc_types as e:
                    logger.debug(
                        f"函数 {func.__name__} "
                        f"第 {attempt + 1}/{retries} 次调用失败: {e!r}"
                    )
                    caught.append(e)
                    await anyio.sleep(delay)

            raise ExceptionGroup(f"所有 {retries} 次尝试均失败", caught) from caught[0]

        return wrapper

    return decorator


class PerfLog:
    def __init__(self, on_start: str, on_end: str) -> None:
        self._on_start = on_start
        self._on_end = on_end
        self._start: float | None = None
        self._end: float | None = None

    def __enter__(self) -> Self:
        self._start = time.perf_counter()
        logger.debug(self._on_start.format(start=self._start))
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        self._end = time.perf_counter()
        logger.debug(self._on_end.format(end=self._end, elapsed=self.elapsed))

    async def __aenter__(self) -> Self:
        return self.__enter__()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        return self.__exit__(exc_type, exc_value, exc_traceback)

    @property
    def start(self) -> float:
        if self._start is None:
            raise ValueError("Start time not set yet")
        return self._start

    @property
    def end(self) -> float:
        if self._end is None:
            raise ValueError("End time not set yet")
        return self._end

    @property
    def elapsed(self) -> float:
        return self.end - self.start

    @classmethod
    def for_action(cls, action: str) -> Self:
        return cls(
            f"Starting {action} at {{start:.2f}}",
            f"Finished {action} at {{end:.2f}}, elapsed {{elapsed:.2f}}s",
        )
