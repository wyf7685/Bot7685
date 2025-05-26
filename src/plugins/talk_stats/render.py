import datetime as dt
import math
from pathlib import Path

from nonebot_plugin_htmlrender import get_new_page, template_to_html
from nonebot_plugin_uninfo.model import User

template_dir = Path(__file__).parent / "templates"


def _get_count_color(count: int, total: int) -> str:
    # sourcery skip: assign-if-exp, reintroduce-else

    if count == 0:
        return "#ebedf0"

    # Normalize the count to a value between 0 and 1
    # Apply an exponential function to the normalized value
    # We use e^(k * normalized - k), where k controls the steepness
    exp_value = math.exp(count / total * 3 - 3)

    # Map the exponential value to color buckets
    if exp_value < 0.1:
        return "#9be9a8"
    if exp_value < 0.3:
        return "#40c463"
    if exp_value < 0.5:
        return "#30a14e"
    return "#216e39"


def construct_cell(
    data: dict[dt.date, int], days: int = 30
) -> tuple[dict[tuple[int, int], str], int, int]:
    if not data:  # 一般来说不会...吧?
        return {}, 0, 0

    last_date = max(data.keys())
    cells = [(x := 0, last_date.weekday(), data[last_date])]
    for day in range(1, days):
        date = last_date - dt.timedelta(days=day)
        y, c = date.weekday(), data.get(date, 0)
        x = x + (y == 6)
        cells.append((x, y, c))
    max_cnt = max(c for _, _, c in cells)
    max_x = max(x for x, _, _ in cells)
    result = {(x, y): _get_count_color(c, max_cnt) for x, y, c in cells}
    return result, max_x, max_cnt


async def render_my(data: dict[dt.date, int], days: int, user: User) -> bytes:
    cells, max_x, max_cnt = construct_cell(data, days)
    container_width = (max(max_x, 5) + 1) * 16
    templates_data = {
        "min": min,
        "cells": cells,
        "max_x": max_x,
        "max_cnt": max_cnt,
        "container_width": container_width,
        "user": user,
        "days": days,
    }

    html = await template_to_html(
        template_path=str(template_dir),
        template_name="my.html.jinja2",
        filters=None,
        **templates_data,
    )

    async with get_new_page(viewport={"width": container_width, "height": 350}) as page:
        await page.set_content(html, wait_until="networkidle")
        if calendar_element := await page.query_selector("#calendar-container"):
            return await calendar_element.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")


def construct_chart(data: list[tuple[User, int]]) -> list[dict[str, object]]:
    percentage_max = max(count for _, count in data) * 1.05
    r1, g1, b1 = 29, 113, 48  # 1d7130
    r2, g2, b2 = 52, 208, 88  # 34d058

    def fn(t: float) -> str:
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    return [
        {
            "name": user.name if user.name is not None else user.id,
            "id": user.id,
            "avatar": user.avatar,
            "count": count,
            "width": f"{(count / percentage_max * 100):.1f}%",
            "color": fn(idx / len(data)),
        }
        for idx, (user, count) in enumerate(
            sorted(data, key=lambda x: x[1], reverse=True)
        )
    ]


async def render_scene(data: list[tuple[User, int]], days: int = 7) -> bytes:
    chart_data = construct_chart(data)
    view_height = 150 + len(chart_data) * 55  # 基础高度 + 每行高度
    templates_data = {
        "chart_data": chart_data,
        "total_messages": sum(count for _, count in data),
        "days": days,
        "container_height": view_height - 50,  # 容器高度略小于视图
    }

    html = await template_to_html(
        template_path=str(template_dir),
        template_name="scene.html.jinja2",
        filters=None,
        **templates_data,
    )

    async with get_new_page(viewport={"width": 600, "height": view_height}) as page:
        await page.set_content(html, wait_until="networkidle")
        if chart_element := await page.query_selector("#chart-container"):
            return await chart_element.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
