import io
import itertools
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

import anyio.to_thread
from nonebot_plugin_htmlrender import get_new_page, template_to_html
from PIL import Image

from .config import TEMPLATE_DIR, TemplateConfig
from .preview import download_preview
from .utils import PAID_COLORS, find_color_name

type RGBA = tuple[int, int, int, int]


class PixelAccess[TPixel](Protocol):
    def __getitem__(self, xy: tuple[int, int]) -> TPixel: ...

    # def __setitem__(self, xy: tuple[int, int], color: TPixel) -> None: ...


@dataclass
class ColorEntry:
    name: str
    rgb: tuple[int, int, int]
    count: int = 0
    total: int = 0

    @property
    def is_paid(self) -> bool:
        return self.name in PAID_COLORS

    @property
    def rgb_str(self) -> str:
        if self.name == "Transparent":
            return "transparent"

        r, g, b = self.rgb
        return f"#{r:02X}{g:02X}{b:02X}"

    @property
    def drawn(self) -> int:
        return self.total - self.count

    @property
    def progress(self) -> float:
        return (self.drawn / self.total * 100) if self.total > 0 else 0


async def calc_template_progress(cfg: TemplateConfig) -> list[ColorEntry]:
    template_img = Image.open(cfg.file)
    width, height = template_img.size
    coord1 = cfg.coords
    coord2 = coord1.offset(width - 1, height - 1)
    actual_img_bytes = await download_preview(coord1, coord2)
    actual_img = Image.open(io.BytesIO(actual_img_bytes))

    def compare() -> list[ColorEntry]:
        template_pixels = cast("PixelAccess[RGBA]", template_img.convert("RGBA").load())
        actual_pixels = cast("PixelAccess[RGBA]", actual_img.convert("RGBA").load())

        diff_pixels: dict[str, ColorEntry] = {}
        for x, y in itertools.product(range(width), range(height)):
            template_pixel = template_pixels[x, y]
            # 跳过模板中的透明像素
            if template_pixel[3] == 0:
                continue

            color_name = find_color_name(template_pixel)
            if color_name not in diff_pixels:
                diff_pixels[color_name] = ColorEntry(color_name, template_pixel[:3])

            # 统计模板像素总数
            diff_pixels[color_name].total += 1

            # 如果模板像素颜色与实际像素颜色不同
            if template_pixel[:3] != actual_pixels[x, y][:3]:
                diff_pixels[color_name].count += 1

        return sorted(
            diff_pixels.values(),
            key=lambda entry: (-entry.total, entry.name),
        )

    return await anyio.to_thread.run_sync(compare)


async def render_progress(progress_data: list[ColorEntry]) -> bytes:
    total_pixels = sum(e.total for e in progress_data)
    remaining_pixels = sum(e.count for e in progress_data)
    drawn_pixels = total_pixels - remaining_pixels
    overall_progress = (drawn_pixels / total_pixels * 100) if total_pixels else 0

    # 基础高度 + 每行高度
    view_height = 150 + len(progress_data) * 66
    template_data = {
        "progress_data": progress_data,
        "title": "模板绘制进度",
        "subtitle": (
            f"总体进度: {drawn_pixels} / {total_pixels} "
            f"({overall_progress:.2f}%)，"
            f"剩余 {remaining_pixels} 像素"
        ),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "container_height": view_height - 50,  # 容器高度略小于视图
    }

    html = await template_to_html(
        template_path=str(TEMPLATE_DIR),
        template_name="progress.html.jinja2",
        **template_data,
    )

    async with get_new_page(viewport={"width": 600, "height": view_height}) as page:
        await page.set_content(html, wait_until="networkidle")
        if container := await page.query_selector("#progress-container"):
            return await container.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
