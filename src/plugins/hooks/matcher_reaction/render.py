import functools
from html import escape as html_escape
from pathlib import Path

from nonebot import logger
from nonebot.utils import escape_tag, run_sync
from nonebot_plugin_htmlrender import get_new_page, template_to_html
from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers.python import PythonTracebackLexer

from .store import ExceptionRecord

TEMPLATE_DIR = Path(__file__).parent / "templates"
STYLE = "one-dark"
# 超长 traceback 渲染成图片没有可读性优势, 反而更难看清
MAX_TRACEBACK_LINES = 200


@functools.cache
def _formatter() -> HtmlFormatter[str]:
    return HtmlFormatter(style=STYLE, nowrap=True)


@functools.cache
def _style_defs() -> str:
    return _formatter().get_style_defs(".traceback")


@functools.cache
def _background() -> str:
    return _formatter().style.background_color


def _truncate(trace: str) -> str:
    lines = trace.splitlines()
    if len(lines) <= MAX_TRACEBACK_LINES:
        return trace
    omitted = len(lines) - MAX_TRACEBACK_LINES
    kept = [*lines[: MAX_TRACEBACK_LINES // 2], f"... ({omitted} 行省略) ..."]
    kept += lines[-(MAX_TRACEBACK_LINES // 2) :]
    return "\n".join(kept)


@run_sync
def _highlight(trace: str) -> str:
    return highlight(_truncate(trace), PythonTracebackLexer(), _formatter())


async def render_traceback(record: ExceptionRecord) -> bytes:
    """将单条异常记录渲染为图片。"""
    html = await template_to_html(
        template_path=str(TEMPLATE_DIR),
        template_name="traceback.html.jinja2",
        style_defs=_style_defs(),
        background=_background(),
        exception=html_escape(record.exception),
        matcher=html_escape(record.matcher),
        source=html_escape(record.source),
        traceback=await _highlight(record.traceback),
    )

    async with get_new_page(viewport={"width": 960, "height": 10}) as page:
        await page.set_content(html, wait_until="networkidle")
        if card := await page.query_selector("#card"):
            return await card.screenshot(type="png")
        return await page.screenshot(full_page=True, type="png")


async def safe_render_traceback(record: ExceptionRecord) -> bytes | None:
    try:
        return await render_traceback(record)
    except Exception as exc:
        logger.opt(colors=True).warning(
            f"渲染 traceback 图片失败: <r>{escape_tag(repr(exc))}</>"
        )
        return None
