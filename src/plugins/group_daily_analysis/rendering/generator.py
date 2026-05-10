"""报告渲染器 — 子模板预渲染 + 主模板拼装 + htmlrender 截图。

头像获取通过 avatar_getter 回调注入，由调用方通过 uninfo Interface 提供，
不依赖任何平台特定 API。
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from nonebot.log import logger
from nonebot_plugin_htmlrender import get_new_page

from ..config import config
from ..services.analysis_service import AnalysisResult
from .avatar import AvatarManager
from .sub_templates import (
    _get_jinja_env,
    render_activity_chart,
    render_chat_quality,
    render_quotes,
    render_topics,
    render_user_titles,
)

if TYPE_CHECKING:
    from nonebot_plugin_uninfo.params import Interface

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"


async def render_image(result: AnalysisResult, interface: Interface) -> bytes | None:
    """将分析结果渲染为图片 bytes。

    Args:
        result: 分析结果
    """
    template_dir = TEMPLATE_DIR / config.render.report_template
    if not template_dir.exists():
        template_dir = TEMPLATE_DIR / "scrapbook"
    if not (template_dir / "image_template.html.jinja2").exists():
        logger.error(f"模板目录缺少 image_template.html.jinja2: {template_dir}")
        return None

    stats = result.statistics
    avatar_manager = AvatarManager(interface)

    # ── 1. 子模板渲染 ──────────────────────────────────────
    (
        topics_html,
        titles_html,
        quotes_html,
        chart_html,
        quality_html,
    ) = await asyncio.gather(
        render_topics(result.topics, template_dir, avatar_manager),
        render_user_titles(result.user_titles, template_dir, avatar_manager),
        render_quotes(result.golden_quotes, template_dir, avatar_manager),
        render_activity_chart(
            stats.activity_visualization.hourly_activity, template_dir
        ),
        render_chat_quality(result.chat_quality, template_dir),
    )

    # ── 2. 拼装 render_data ────────────────────────────────
    now = datetime.now()
    render_data: dict[str, Any] = {
        "t2i_font_source": "Mainland",
        "t2i_google_fonts_mirror": "https://fonts.loli.net",
        "t2i_gstatic_mirror": "https://gstatic.loli.net",
        "current_date": f"{now.year}年{now.month:02d}月{now.day:02d}日",
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "group_name": result.group_name,
        "message_count": stats.message_count,
        "participant_count": stats.participant_count,
        "total_characters": stats.total_characters,
        "emoji_count": stats.emoji_count,
        "most_active_period": stats.most_active_period,
        "topics_html": topics_html,
        "titles_html": titles_html,
        "quotes_html": quotes_html,
        "hourly_chart_html": chart_html,
        "chat_quality_html": quality_html,
        "total_tokens": result.token_usage.total_tokens,
        "prompt_tokens": result.token_usage.prompt_tokens,
        "completion_tokens": result.token_usage.completion_tokens,
    }

    # ── 3. 渲染主模板 + 截图 ───────────────────────────────
    return await _render_to_image(
        template_dir, "image_template.html.jinja2", render_data, avatar_manager
    )


async def _render_to_image(
    template_dir: Path,
    template_name: str,
    render_data: dict[str, Any],
    avatar_manager: AvatarManager,
) -> bytes | None:
    try:
        env = _get_jinja_env(template_dir)
        html = await env.get_template(template_name).render_async(**render_data)

        # 应用头像 CSS 复用，减小 HTML 体积
        html = avatar_manager.reuse.apply(html)

        scale = config.render.device_scale_factor
        timeout = min(config.render.render_timeout, 5000)

        async with get_new_page(
            viewport={"width": 800, "height": 2000},
            device_scale_factor=scale,
        ) as page:
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(timeout)
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 800, "height": height + 50})
            container = await page.query_selector("#report-container")
            if container:
                return await container.screenshot(type="png")
            return await page.screenshot(full_page=True, type="png")

    except Exception:
        logger.exception("图片渲染失败")
        return None
