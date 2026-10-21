from pathlib import Path

from nonebot_plugin_htmlrender import render_template

from .models import ScheduleData

template_dir = Path(__file__).parent / "templates"


async def render_schedule(data: ScheduleData) -> bytes:
    rendered = await render_template(
        template_path=template_dir,
        template_name="schedule.html.jinja2",
        variables={"entries": data.entries},
    )
    return rendered.data
