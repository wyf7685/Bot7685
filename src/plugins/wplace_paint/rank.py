from collections.abc import Iterable
from dataclasses import dataclass

import anyio
from nonebot_plugin_htmlrender import get_new_page, template_to_html

from .avartar import get_wplace_avatar
from .config import TEMPLATE_DIR
from .fetch import (
    PixelRegion,
    RankType,
    RequestFailed,
    fetch_region_rank,
    get_pixel_info,
)
from .utils import WplaceAbsCoords, WplacePixelCoords, fix_coords, get_flag_emoji


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
    checked_coords: dict[WplaceAbsCoords, int] = {}

    async def get_region_id_at(
        abs_x: int, abs_y: int, found: dict[int, PixelRegion] = found_region
    ) -> int | None:
        """根据绝对像素坐标获取 region ID，并处理缓存和异常。"""
        coord = WplaceAbsCoords(abs_x, abs_y)
        if coord in checked_coords:
            region_id = checked_coords[coord]
            found[region_id] = found_region[region_id]
            return region_id

        try:
            pixel_info = await get_pixel_info(coord.to_pixel())
        except RequestFailed:
            # 如果查询失败，则忽略该点
            return None

        region_id = pixel_info.region.id
        found[region_id] = pixel_info.region
        checked_coords[coord] = region_id
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

    # 将坐标转换为绝对像素坐标，便于计算
    c1, c2 = fix_coords(coord1, coord2)
    await subdivide(*c1.to_abs(), *c2.to_abs())
    return found_region


@dataclass
class RankData:
    user_id: int
    name: str
    picture: str | None
    flag: int
    pixels: int = 0


async def get_regions_rank(
    region_ids: Iterable[int],
    rank_type: RankType,
) -> list[RankData]:
    result: dict[int, RankData] = {}
    lock = anyio.Lock()

    async def fetch(region_id: int) -> None:
        try:
            users = await fetch_region_rank(region_id, rank_type)
        except RequestFailed:
            return

        async with lock:
            for user in users:
                if user.id not in result:
                    result[user.id] = RankData(
                        user.id,
                        user.name,
                        user.picture,
                        user.equippedFlag,
                    )
                result[user.id].pixels += user.pixelsPainted

    async with anyio.create_task_group() as tg:
        for rid in region_ids:
            tg.start_soon(fetch, rid)

    return sorted(result.values(), key=lambda x: x.pixels, reverse=True)


RANK_TITLE: dict[RankType, str] = {
    "today": "今日排行榜",
    "week": "本周排行榜",
    "month": "本月排行榜",
    "all-time": "历史总排行榜",
}

_RANK_COLORS = (29, 113, 48), (52, 208, 88)


async def render_rank(
    rank_type: RankType,
    rank_data: list[RankData],
) -> bytes:
    title = RANK_TITLE[rank_type]
    subtitle = f"共计 {sum(r.pixels for r in rank_data)} 像素"
    max_cnt = max(r.pixels for r in rank_data)
    (r1, g1, b1), (r2, g2, b2) = _RANK_COLORS

    def fn(t: float) -> str:
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    chart_data = [
        {
            "id": r.user_id if not r.flag else f"{r.user_id} {get_flag_emoji(r.flag)}",
            "name": r.name,
            "count": r.pixels,
            "width": f"{r.pixels / max_cnt * 100:.1f}%",
            "color": fn(idx / len(rank_data)),
            "avatar": r.picture or get_wplace_avatar(str(r.user_id)),
        }
        for idx, r in enumerate(rank_data)
    ]
    view_height = 150 + len(chart_data) * 55  # 基础高度 + 每行高度
    template_data = {
        "chart_data": chart_data,
        "title": title,
        "subtitle": subtitle,
        "container_height": view_height - 50,  # 容器高度略小于视图
    }

    html = await template_to_html(
        template_path=str(TEMPLATE_DIR),
        template_name="rank.html.jinja2",
        filters=None,
        **template_data,
    )

    async with get_new_page(viewport={"width": 600, "height": view_height}) as page:
        await page.set_content(html, wait_until="networkidle")
        if container := await page.query_selector("#chart-container"):
            return await container.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
