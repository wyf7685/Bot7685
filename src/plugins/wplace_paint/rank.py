from collections.abc import Iterable

import anyio

from .fetch import (
    PixelRegion,
    RankType,
    RequestFailed,
    fetch_region_rank,
    get_pixel_info,
)
from .utils import WplacePixelCoords, fix_coords


async def find_regions_in_rect(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> dict[int, PixelRegion]:
    """
    通过递归细分算法查找给定矩形区域内的所有 region ID。

    :param coord1: 矩形的一个角点坐标。
    :param coord2: 矩形的对角坐标。
    :return: 一个包含所有不重复 region ID 的集合。
    """
    # 使用一个 dict 来自动处理重复的 region ID
    found_region: dict[int, PixelRegion] = {}
    # 使用一个 dict 来缓存已查询过的坐标，避免重复 API 调用
    checked_coords: dict[tuple[int, int, int, int], int] = {}

    # 将坐标转换为绝对像素坐标，便于计算
    c1, c2 = fix_coords(coord1, coord2)
    x1 = c1.tlx * 1000 + c1.pxx
    y1 = c1.tly * 1000 + c1.pxy
    x2 = c2.tlx * 1000 + c2.pxx
    y2 = c2.tly * 1000 + c2.pxy

    async def get_region_id_at(
        abs_x: int,
        abs_y: int,
        found: dict[int, PixelRegion] = found_region,
    ) -> int | None:
        """根据绝对像素坐标获取 region ID，并处理缓存和异常。"""
        coord_key = (abs_x // 1000, abs_y // 1000, abs_x % 1000, abs_y % 1000)
        if coord_key in checked_coords:
            region_id = checked_coords[coord_key]
            found[region_id] = found_region[region_id]
            return region_id

        try:
            pixel_info = await get_pixel_info(WplacePixelCoords(*coord_key))
        except RequestFailed:
            # 如果查询失败，则忽略该点
            return None
        else:
            region_id = pixel_info.region.id
            found[region_id] = pixel_info.region
            checked_coords[coord_key] = region_id
            return region_id

    async def subdivide(left: int, top: int, right: int, bottom: int) -> None:
        """递归细分函数。"""
        # 检查四个角点
        corners: dict[int, PixelRegion] = {}
        async with anyio.create_task_group() as tg:
            tg.start_soon(get_region_id_at, left, top, corners)  # 左上
            tg.start_soon(get_region_id_at, right, top, corners)  # 右上
            tg.start_soon(get_region_id_at, left, bottom, corners)  # 左下
            tg.start_soon(get_region_id_at, right, bottom, corners)  # 右下

        async def sub(mid_x: int, mid_y: int) -> None:
            async with anyio.create_task_group() as tg:
                tg.start_soon(subdivide, left, top, mid_x, mid_y)  # 左上
                tg.start_soon(subdivide, mid_x, top, right, mid_y)  # 右上
                tg.start_soon(subdivide, left, mid_y, mid_x, bottom)  # 左下
                tg.start_soon(subdivide, mid_x, mid_y, right, bottom)  # 右下

        # 如果所有角点都相同（或只有一个角点成功返回），并且矩形不是最小单位
        if len(corners) <= 1 and (left < right or top < bottom):
            # 检查中心点以确认区域内部是否一致
            mid_x, mid_y = (left + right) // 2, (top + bottom) // 2
            center_region = await get_region_id_at(mid_x, mid_y)

            # 如果中心点与角点区域不同，则需要细分
            if center_region is not None and center_region not in corners:
                # 递归处理四个象限
                await sub(mid_x, mid_y)

        # 如果角点不一致，说明已跨越边界，直接细分
        elif len(corners) > 1:
            # 递归处理四个象限
            await sub((left + right) // 2, (top + bottom) // 2)

    await subdivide(x1, y1, x2, y2)
    return found_region


async def get_regions_rank(
    region_ids: Iterable[int],
    rank_type: RankType,
) -> list[tuple[int, str, int]]:
    # user_id -> pixelsPainted
    painted: dict[int, int] = {}
    names: dict[int, str] = {}
    lock = anyio.Lock()

    async def fetch(region_id: int) -> None:
        try:
            users = await fetch_region_rank(region_id, rank_type)
        except RequestFailed:
            return

        async with lock:
            for user in users:
                names[user.id] = user.name
                painted[user.id] = painted.get(user.id, 0) + user.pixelsPainted

    async with anyio.create_task_group() as tg:
        for rid in region_ids:
            tg.start_soon(fetch, rid)

    return [
        (user_id, names[user_id], count)
        for user_id, count in sorted(painted.items(), key=lambda x: x[1], reverse=True)
    ]
