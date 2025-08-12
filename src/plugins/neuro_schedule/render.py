from pathlib import Path

from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_htmlrender import html_to_pic, template_to_html

template_dir = Path(__file__).parent / "templates"


async def render_schedule(lines: list[UniMessage]) -> bytes:  # noqa: ARG001
    # TODO: do something to process schedule lines ...
    templates_data = {}

    html = await template_to_html(
        template_path=str(template_dir),
        template_name="schedule.html.jinja2",
        filters=None,
        **templates_data,
    )

    return await html_to_pic(html)
