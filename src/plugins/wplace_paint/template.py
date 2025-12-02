import io
import itertools
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, cast

import anyio
import anyio.to_thread
import bot7685_ext.wplace
import httpx
from bot7685_ext.wplace import ColorEntry
from nonebot import logger
from nonebot.utils import run_sync
from nonebot_plugin_htmlrender import get_new_page, template_to_html
from PIL import Image

from src.utils import with_semaphore

from .config import TEMPLATE_DIR, TemplateConfig, proxy
from .utils import (
    PerfLog,
    WplacePixelCoords,
    find_color_name,
    parse_rgb_str,
    with_retry,
)

type RGBA = tuple[int, int, int, int]


class PixelAccess[TPixel](Protocol):
    def __getitem__(self, xy: tuple[int, int]) -> TPixel: ...
    def __setitem__(self, xy: tuple[int, int], color: TPixel) -> None: ...


logger = logger.opt(colors=True)


@PerfLog.for_method()
async def download_preview(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
    background: str | None = None,
) -> bytes:
    coord1, coord2 = coord1.fix_with(coord2)
    tile_imgs: dict[tuple[int, int], bytes] = {}
    logger.info(
        f"Downloading preview from <y>{coord1.human_repr()}</> "
        f"to <y>{coord2.human_repr()}</>"
    )

    @with_semaphore(4)
    @with_retry(
        *(httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError),
        delay=1,
    )
    async def fetch_tile(x: int, y: int) -> None:
        resp = await client.get(
            f"https://backend.wplace.live/files/s0/tiles/{x}/{y}.png"
        )
        tile_imgs[(x, y)] = resp.raise_for_status().read()

    async with (
        PerfLog.for_action("downloading tiles") as perf,
        httpx.AsyncClient(proxy=proxy) as client,
        anyio.create_task_group() as tg,
    ):
        for x, y in coord1.all_tile_coords(coord2):
            tg.start_soon(fetch_tile, x, y)
    logger.info(f"Downloaded <g>{len(tile_imgs)}</> tiles (<y>{perf.elapsed:.2f}</>s)")

    def create_image() -> bytes:
        bg_color = (0, 0, 0, 0)
        if background is not None and (bg_rgb := parse_rgb_str(background)):
            bg_color = (*bg_rgb, 255)

        img = Image.new("RGBA", coord1.size_with(coord2), bg_color)
        for (tx, ty), tile_bytes in tile_imgs.items():
            tile_img = Image.open(io.BytesIO(tile_bytes)).convert("RGBA")
            src_box = (
                0 if tx != coord1.tlx else coord1.pxx,
                0 if ty != coord1.tly else coord1.pxy,
                1000 if tx != coord2.tlx else coord2.pxx + 1,
                1000 if ty != coord2.tly else coord2.pxy + 1,
            )
            paste_pos = (
                (tx - coord1.tlx) * 1000 - (0 if tx == coord1.tlx else coord1.pxx),
                (ty - coord1.tly) * 1000 - (0 if ty == coord1.tly else coord1.pxy),
            )
            src = tile_img.crop(src_box)
            img.paste(src, paste_pos, src.getchannel("A"))

        with io.BytesIO() as output:
            img.save(output, format="PNG")
            return output.getvalue()

    with PerfLog.for_action("creating image") as perf:
        image = await anyio.to_thread.run_sync(create_image)
    logger.info(f"Created image in <y>{perf.elapsed:.2f}</>s")
    return image


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


@PerfLog.for_method()
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


@PerfLog.for_method()
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
        filters=None,
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
