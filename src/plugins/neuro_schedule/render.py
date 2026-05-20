from pathlib import Path

from nonebot_plugin_htmlrender import get_new_page, template_to_html

from .models import ScheduleData

template_dir = Path(__file__).parent / "templates"


async def render_schedule(data: ScheduleData) -> bytes:
    html = await template_to_html(
        template_path=str(template_dir),
        template_name="schedule.html.jinja2",
        entries=data.entries,
    )
    async with get_new_page(device_scale_factor=2) as page:
        await page.set_content(html, wait_until="networkidle")
        await page.wait_for_timeout(500)
        if container := await page.query_selector(".card"):
            return await container.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
