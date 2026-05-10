"""子模板渲染 — 话题、用户称号、金句、图表、质量锐评。"""

import asyncio
import dataclasses
from pathlib import Path
from typing import Any

import jinja2
from nonebot.log import logger
from nonebot.utils import escape_tag

from ..config import config
from ..domain.models import GoldenQuote, QualityReview, SummaryTopic, UserTitle
from .avatar import AvatarManager
from .mentions import render_mentions
from .profile import ProfileResolver


def get_jinja_env(template_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
        enable_async=True,
    )


async def render_sub_template(
    template_dir: Path,
    template_name: str,
    **kwargs: Any,
) -> str:
    try:
        env = get_jinja_env(template_dir)
        return await env.get_template(template_name).render_async(**kwargs)
    except Exception as e:
        logger.warning(f"子模板渲染失败 ({template_name}): {escape_tag(str(e))}")
        return ""


async def render_topics(
    topics: list[SummaryTopic],
    template_dir: Path,
    avatar_manager: AvatarManager,
) -> str:
    if not topics:
        return ""

    async def render_one(index: int, topic: SummaryTopic) -> dict[str, Any]:
        detail = await render_mentions(topic.detail, avatar_manager)
        return {
            "index": index,
            "topic": topic.topic,
            "contributors": "、".join(topic.contributors),
            "detail": detail,
        }

    items = await asyncio.gather(*(render_one(*item) for item in enumerate(topics, 1)))
    return await render_sub_template(
        template_dir, "topic_item.html.jinja2", topics=items
    )


async def render_user_titles(
    titles: list[UserTitle],
    template_dir: Path,
    avatar_manager: AvatarManager,
) -> str:
    if not titles:
        return ""

    profile_resolver = ProfileResolver(config.render.profile_display_mode)

    async def render_one(u: UserTitle) -> dict[str, Any]:
        avatar_data, _ = await avatar_manager.get_avatar(u.user_id)
        return {
            **dataclasses.asdict(u),
            "avatar_data": avatar_data,
            **profile_resolver.resolve(u.mbti),
        }

    items = await asyncio.gather(*(render_one(u) for u in titles))
    return await render_sub_template(
        template_dir, "user_title_item.html.jinja2", titles=items
    )


async def render_quotes(
    quotes: list[GoldenQuote],
    template_dir: Path,
    avatar_manager: AvatarManager,
) -> str:
    if not quotes:
        return ""

    async def render_one(q: GoldenQuote) -> dict[str, Any]:
        avatar_data, _ = await avatar_manager.get_avatar(q.user_id)
        reason = await render_mentions(q.reason, avatar_manager)
        return {
            "content": q.content,
            "sender": q.sender,
            "reason": reason,
            "avatar_url": avatar_data,
        }

    items = await asyncio.gather(*(render_one(q) for q in quotes))
    return await render_sub_template(
        template_dir, "quote_item.html.jinja2", quotes=items
    )


async def render_activity_chart(
    hourly_activity: dict[int, int],
    template_dir: Path,
) -> str:
    if not hourly_activity:
        return ""

    chart_data = []
    max_activity = max(hourly_activity.values()) if hourly_activity else 1

    for hour in range(24):
        count = hourly_activity.get(hour, 0)
        percentage = (count / max_activity) * 100 if max_activity > 0 else 0
        chart_data.append(
            {"hour": hour, "count": count, "percentage": round(percentage, 1)}
        )

    return await render_sub_template(
        template_dir,
        "activity_chart.html.jinja2",
        chart_data=chart_data,
    )


async def render_chat_quality(
    quality: QualityReview | None,
    template_dir: Path,
) -> str:
    if not quality:
        return ""
    return await render_sub_template(
        template_dir,
        "chat_quality_item.html.jinja2",
        **dataclasses.asdict(quality),
    )
