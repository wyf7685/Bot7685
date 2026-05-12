"""子模板渲染 — 话题、用户称号、金句、图表、质量锐评。"""

import asyncio
import dataclasses
from typing import Any

import jinja2
from nonebot.log import logger
from nonebot.utils import escape_tag

from ..config import TEMPLATE_DIR, config
from ..domain.models import GoldenQuote, QualityReview, SummaryTopic, UserTitle
from .avatar import AvatarManager
from .mentions import render_mentions
from .profile import ProfileResolver


class TemplateManager:
    REQUIRED_TEMPLATES = (
        "activity_chart.html.jinja2",
        "chat_quality_item.html.jinja2",
        "image_template.html.jinja2",
        "quote_item.html.jinja2",
        "topic_item.html.jinja2",
        "user_title_item.html.jinja2",
    )

    def __init__(self) -> None:
        template_dir = TEMPLATE_DIR / config.render.report_template
        if not template_dir.exists():
            template_dir = TEMPLATE_DIR / "scrapbook"
        self.template_dir = template_dir
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=jinja2.select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
            enable_async=True,
        )

    def is_valid(self) -> bool:
        return all(
            self.template_dir.joinpath(tpl).exists() for tpl in self.REQUIRED_TEMPLATES
        )

    async def render(self, template_name: str, /, **kwargs: Any) -> str:
        try:
            return await self.env.get_template(template_name).render_async(**kwargs)
        except Exception as e:
            logger.warning(f"模板渲染失败 ({template_name}): {escape_tag(str(e))}")
            return ""


async def render_topics(
    topics: list[SummaryTopic],
    template: TemplateManager,
    avatar_manager: AvatarManager,
) -> str:
    if not topics:
        return ""

    async def prepare_one(i: int, t: SummaryTopic) -> dict[str, Any]:
        detail = await render_mentions(t.detail, avatar_manager)
        return {
            "index": i,
            "topic": t.topic,
            "contributors": "、".join(t.contributors),
            "detail": detail,
        }

    items = await asyncio.gather(*(prepare_one(i, t) for i, t in enumerate(topics, 1)))
    return await template.render("topic_item.html.jinja2", topics=items)


async def render_user_titles(
    titles: list[UserTitle],
    template: TemplateManager,
    avatar_manager: AvatarManager,
) -> str:
    if not titles:
        return ""

    profile_resolver = ProfileResolver(config.render.profile_display_mode)

    async def prepare_one(u: UserTitle) -> dict[str, Any]:
        avatar_data = await avatar_manager.get_avatar(u.user_id)
        return {
            **dataclasses.asdict(u),
            "avatar_data": avatar_data,
            **profile_resolver.resolve(u.mbti),
        }

    items = await asyncio.gather(*(prepare_one(u) for u in titles))
    return await template.render("user_title_item.html.jinja2", titles=items)


async def render_quotes(
    quotes: list[GoldenQuote],
    template: TemplateManager,
    avatar_manager: AvatarManager,
) -> str:
    if not quotes:
        return ""

    async def prepare_one(q: GoldenQuote) -> dict[str, Any]:
        avatar_data = await avatar_manager.get_avatar(q.user_id)
        reason = await render_mentions(q.reason, avatar_manager)
        return {
            "content": q.content,
            "sender": q.sender,
            "reason": reason,
            "avatar_url": avatar_data,
        }

    items = await asyncio.gather(*(prepare_one(q) for q in quotes))
    return await template.render("quote_item.html.jinja2", quotes=items)


async def render_activity_chart(
    hourly_activity: dict[int, int],
    template: TemplateManager,
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

    return await template.render("activity_chart.html.jinja2", chart_data=chart_data)


async def render_chat_quality(
    quality: QualityReview | None,
    template: TemplateManager,
) -> str:
    if not quality:
        return ""
    return await template.render(
        "chat_quality_item.html.jinja2",
        **dataclasses.asdict(quality),
    )
