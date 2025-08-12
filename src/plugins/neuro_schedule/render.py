from pathlib import Path
from typing import Any

from nonebot_plugin_alconna import Image, UniMessage
from nonebot_plugin_htmlrender import get_new_page, template_to_html

template_dir = Path(__file__).parent / "templates"


async def render_schedule(lines: list[UniMessage]) -> bytes:
    formatted_lines: list[dict[str, Any]] = [
        {"text": line.extract_plain_text(), "images": [i for i in line[Image] if i.url]}
        for line in lines
    ]
    templates_data = {"lines": formatted_lines}

    html = await template_to_html(
        template_path=str(template_dir),
        template_name="schedule.html.jinja2",
        filters=None,
        **templates_data,
    )

    async with get_new_page(viewport={"width": 325, "height": 650}) as page:
        await page.set_content(html, wait_until="networkidle")
        if container := await page.query_selector(".container"):
            return await container.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
