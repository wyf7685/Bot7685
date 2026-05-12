"""报告渲染器 — 子模板预渲染 + 主模板拼装 + htmlrender 截图。"""

import asyncio
from datetime import datetime
from typing import Any

from nonebot.log import logger
from nonebot_plugin_htmlrender import get_new_page

from ..config import config
from ..services.analysis_service import AnalysisResult
from .avatar import AvatarManager
from .sub_templates import (
    TemplateManager,
    render_activity_chart,
    render_chat_quality,
    render_quotes,
    render_topics,
    render_user_titles,
)


async def render_image(result: AnalysisResult) -> bytes | None:
    """将分析结果渲染为图片 bytes。

    Args:
        result: 分析结果
    """
    template = TemplateManager()
    if not template.is_valid():
        logger.error(f"无效的模板目录: {template.template_dir}")
        return None

    avatar_manager = AvatarManager(result.members)

    # ── 1. 子模板渲染 ──────────────────────────────────────
    (
        topics_html,
        titles_html,
        quotes_html,
        chart_html,
        quality_html,
    ) = await asyncio.gather(
        render_topics(result.topics, template, avatar_manager),
        render_user_titles(result.user_titles, template, avatar_manager),
        render_quotes(result.golden_quotes, template, avatar_manager),
        render_activity_chart(result.statistics.activity.hourly_activity, template),
        render_chat_quality(result.chat_quality, template),
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
        "message_count": result.statistics.message_count,
        "participant_count": result.statistics.participant_count,
        "total_characters": result.statistics.total_characters,
        "emoji_count": result.statistics.emoji_count,
        "most_active_period": result.statistics.most_active_period,
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
    full_html = await template.render("image_template.html.jinja2", **render_data)
    full_html = avatar_manager.apply_reuse(full_html)
    return await _render_to_image(full_html)


async def _render_to_image(html: str) -> bytes | None:
    try:
        async with get_new_page(
            device_scale_factor=config.render.device_scale_factor
        ) as page:
            await page.set_content(html, wait_until="networkidle")
            return await page.screenshot(full_page=True, type="png")
    except Exception:
        logger.exception("图片渲染失败")
        return None
