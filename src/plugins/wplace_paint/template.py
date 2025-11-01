import io
import itertools
from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, cast

import bot7685_ext.wplace
from bot7685_ext.wplace import ColorEntry
from nonebot import logger
from nonebot.utils import run_sync
from nonebot_plugin_htmlrender import get_new_page, template_to_html
from PIL import Image

from src.utils import with_semaphore

from .config import TEMPLATE_DIR, TemplateConfig, UserConfig
from .preview import download_preview
from .utils import PerfLog, WplacePixelCoords, find_color_name, parse_rgb_str

type RGBA = tuple[int, int, int, int]


class PixelAccess[TPixel](Protocol):
    def __getitem__(self, xy: tuple[int, int]) -> TPixel: ...
    def __setitem__(self, xy: tuple[int, int], color: TPixel) -> None: ...


logger = logger.opt(colors=True)


async def download_template_preview(
    cfg: TemplateConfig,
    background: str | None = None,
    border_pixels: int = 0,
) -> bytes:
    _, (coord1, coord2) = cfg.load()
    if border_pixels > 0:
        coord1 = coord1.offset(-border_pixels, -border_pixels)
        coord2 = coord2.offset(border_pixels, border_pixels)
    return await download_preview(coord1, coord2, background)


async def calc_template_diff(
    cfg: TemplateConfig,
    *,
    include_pixels: bool = False,
) -> list[ColorEntry]:
    template_img, coords = cfg.load()
    with io.BytesIO() as buffer:
        template_img.save(buffer, format="PNG")
        template_bytes = buffer.getvalue()
    actual_bytes = await download_preview(*coords)

    with PerfLog.for_action("calculating template diff") as perf:
        diff = await bot7685_ext.wplace.compare(
            template_bytes, actual_bytes, include_pixels
        )
    logger.info(f"Calculated template diff in <y>{perf.elapsed:.3f}</>s")
    logger.info(f"Template diff count: <y>{sum(e.count for e in diff)}</> pixels")

    return diff


async def render_progress(progress_data: list[ColorEntry]) -> bytes:
    total_pixels = sum(e.total for e in progress_data)
    remaining_pixels = sum(e.count for e in progress_data)
    drawn_pixels = total_pixels - remaining_pixels
    overall_progress = (drawn_pixels / total_pixels * 100) if total_pixels else 0

    template_data = {
        "incomplete_colors": sorted(
            filter(lambda e: e.count > 0, progress_data),
            key=lambda e: (-e.progress, -e.total, e.name),
        ),
        "completed_colors": sorted(
            filter(lambda e: e.count == 0 and e.total > 0, progress_data),
            key=lambda e: e.total,
        ),
        "title": "模板绘制进度",
        "subtitle": (
            f"总体进度: {drawn_pixels} / {total_pixels} "
            f"({overall_progress:.2f}%)，"
            f"剩余 {remaining_pixels} 像素"
        ),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    html = await template_to_html(
        template_path=str(TEMPLATE_DIR),
        template_name="progress.html.jinja2",
        **template_data,
    )

    viewport = {"width": 600, "height": 144 + len(progress_data) * 58}
    async with get_new_page(viewport=viewport) as page:
        await page.set_content(html, wait_until="networkidle")
        if container := await page.query_selector("#progress-container"):
            return await container.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")


@run_sync
def render_template_with_color(
    cfg: TemplateConfig,
    colors: Iterable[str],
    background: str | None = None,
) -> bytes:
    colors = set(colors)
    fill_rgba: tuple[int, int, int, int] = (
        (*bg_rgb, 255)
        if background and (bg_rgb := parse_rgb_str(background))
        else (255, 255, 255, 0)
    )
    template_img = Image.open(cfg.file).convert("RGBA")
    width, height = template_img.size
    pixels = cast("PixelAccess[RGBA]", template_img.load())
    for x, y in itertools.product(range(width), range(height)):
        r, g, b, a = pixels[x, y]
        if a != 0 and find_color_name((r, g, b, a)) not in colors:
            pixels[x, y] = fill_rgba

    with io.BytesIO() as output:
        template_img.save(output, format="PNG")
        return output.getvalue()


async def get_color_location(cfg: TemplateConfig, color: str) -> list[tuple[int, int]]:
    diff = await calc_template_diff(cfg, include_pixels=True)
    for entry in diff:
        if entry.name == color:
            return entry.pixels
    return []


def _group_paint_pixels(
    count: int,
    coords: WplacePixelCoords,
    entries: Iterable[ColorEntry],
) -> dict[tuple[int, int], list[tuple[tuple[int, int], int]]]:
    grouped = defaultdict[tuple[int, int], list[tuple[tuple[int, int], int]]](list)
    grouped_count = 0
    for entry in entries:
        remaining = min(count - grouped_count, entry.count)
        if remaining <= 0:
            break
        for x, y in entry.pixels[:remaining]:
            c = coords.offset(x, y)
            grouped[(c.tlx, c.tly)].append(((c.pxx, c.pxy), entry.id))
        grouped_count += remaining
    return grouped


@with_semaphore(1)
async def post_paint(
    user: UserConfig,
    tp: TemplateConfig,
) -> tuple[int, dict[str, int]]:
    raise NotImplementedError

    # user_info = await fetch_me(user)
    # logger.info(f"User has <y>{user_info.charges.count:.2f}</> available pixels")
    # if user_info.charges.count < 1:
    #     return 0, {}

    # diff = await calc_template_diff(tp, include_pixels=True)
    # grouped = _group_paint_pixels(
    #     int(user_info.charges.count),
    #     tp.coords,
    #     filter(lambda e: e.name in user_info.own_colors and e.count, diff),
    # )
    # logger.info(f"Grouped pixels into <y>{len(grouped)}</> tiles for painting")
    # if not sum(map(len, grouped.values())):
    #     return 0, {}

    # await anyio.sleep(random.uniform(0.5, 2))

    # async def _paint_tile(
    #     tile: tuple[int, int],
    #     pixels: list[tuple[tuple[int, int], int]],
    # ) -> None:
    #     await post_paint_pixels(user, tile, pixels)
    #     logger.info(f"Painted <y>{len(pixels)}</> pixels at tile <c>{tile}</>")
    #     color_counter.update(Counter(id for _, id in pixels))

    # color_counter = Counter[int]()
    # async with anyio.create_task_group() as tg:
    #     for tile, pixels in grouped.items():
    #         tg.start_soon(_paint_tile, tile, pixels)

    # painted = sum(color_counter.values())
    # logger.info(f"Total painted pixels: <y>{painted}</>")
    # return painted, {
    #     COLORS_MAP[color_id]["name"]: count
    #     for color_id, count in color_counter.items()
    # }


def format_post_paint_result(painted: int, color_map: dict[str, int]) -> str:
    if painted == 0:
        return "未绘制任何像素，可能是模板已完成或账户无可用像素"

    lines = [f"成功绘制 {painted} 个像素，颜色分布如下:"]
    lines.extend(
        f"- {color_name}: {count} 像素"
        for color_name, count in sorted(
            color_map.items(),
            key=lambda item: (-item[1], item[0]),
        )
    )
    return "\n".join(lines)


async def render_template_overlay(
    cfg: TemplateConfig,
    overlay_alpha: int | None = None,
) -> bytes:
    template_img, (coord1, coord2) = cfg.load()
    with io.BytesIO() as buffer:
        template_img.save(buffer, format="PNG")
        template_bytes = buffer.getvalue()
    actual_bytes = await download_preview(coord1, coord2)

    with PerfLog.for_action("rendering template overlay") as perf:
        overlaid_bytes = await bot7685_ext.wplace.overlay(
            template_bytes,
            actual_bytes,
            overlay_alpha if overlay_alpha is not None else 96,
        )
    logger.info(f"Rendered template overlay in <y>{perf.elapsed:.3f}</>s")

    return overlaid_bytes
