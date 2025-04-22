import datetime as dt
from pathlib import Path

from nonebot_plugin_htmlrender import get_new_page, template_to_html

template_dir = Path(__file__).parent / "templates"


def _get_count_color(count: int) -> str:
    # sourcery skip: assign-if-exp, reintroduce-else
    if count == 0:
        return "#ebedf0"
    if count < 5:
        return "#9be9a8"
    if count < 10:
        return "#40c463"
    if count < 20:
        return "#30a14e"
    return "#216e39"


def construct_cell(
    data: dict[dt.date, int], days: int = 30
) -> tuple[dict[tuple[int, int], int], int]:
    last_date = max(data.keys()) if data else dt.datetime.now().date()
    result = [(x := 0, last_date.weekday(), data[last_date])]
    for day in range(1, days):
        date = last_date - dt.timedelta(days=day)
        y, c = date.weekday(), data.get(date, 0)
        x = x + (y == 6)
        result.append((x, y, c))
    return {(x, y): c for x, y, c in result}, max(x for x, _, _ in result)


async def render_my(data: dict[dt.date, int], days: int = 30) -> bytes:
    cells, max_x = construct_cell(data, days)
    templates_data = {
        "min": min,
        "count_color": _get_count_color,
        "cells": cells,
        "max_x": max_x,
    }

    html = await template_to_html(
        template_path=str(template_dir),
        template_name="my.html.jinja2",
        filters=None,
        **templates_data,
    )

    async with get_new_page() as page:
        await page.set_content(html, wait_until="networkidle")
        if calendar_element := await page.query_selector("#calendar-container"):
            return await calendar_element.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
