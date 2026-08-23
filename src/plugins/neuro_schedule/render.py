from pathlib import Path

from nonebot_plugin_htmlrender import get_default_application, render_template_html

from .models import ScheduleData

template_dir = Path(__file__).parent / "templates"


async def render_schedule(data: ScheduleData) -> bytes:
    rendered = await render_template_html(
        template_path=template_dir,
        template_name="schedule.html.jinja2",
        variables={"entries": data.entries},
    )
    async with get_default_application().extensions.playwright.page(
        device_scale_factor=2,
    ) as page:
        await page.set_content(rendered.content, wait_until="networkidle")
        if card := await page.query_selector(".card"):
            return await card.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")
