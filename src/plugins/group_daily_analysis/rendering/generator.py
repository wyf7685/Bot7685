"""报告渲染器 — 子模板预渲染 + 主模板拼装 + htmlrender 截图。

头像获取通过 avatar_getter 回调注入，由调用方通过 uninfo Interface 提供，
不依赖任何平台特定 API。
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jinja2
from nonebot.log import logger
from nonebot.utils import escape_tag
from nonebot_plugin_htmlrender import get_new_page

from src.service.cache import get_cache

from ..config import config
from ..domain.models import GoldenQuote, QualityReview, SummaryTopic, UserTitle
from ..services.analysis_service import AnalysisResult

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
PROFILE_MANIFEST_PATH = (
    Path(__file__).parent.parent / "assets" / "profile_assets" / "manifest.json"
)

_avatar_cache = get_cache[str]("group_daily_avatar", pickle=False)

# avatar_getter: user_id -> avatar_url (跨平台)
AvatarGetter = Callable[[str], Awaitable[str | None]]


async def render_image(
    result: AnalysisResult,
    avatar_getter: AvatarGetter | None = None,
) -> bytes | None:
    """将分析结果渲染为图片 bytes。

    Args:
        result: 分析结果
        avatar_getter: 异步回调，接收 user_id 返回头像 URL。
                       由调用方通过 uninfo Interface.get_user(uid).avatar 提供。
    """
    template_dir = TEMPLATE_DIR / config.render.report_template
    if not template_dir.exists():
        template_dir = TEMPLATE_DIR / "scrapbook"
    if not (template_dir / "image_template.html.jinja2").exists():
        logger.error(f"模板目录缺少 image_template.html.jinja2: {template_dir}")
        return None

    stats = result.statistics

    # ── 1. 子模板渲染 ──────────────────────────────────────
    topics_html = await _render_topics(result.topics, template_dir, avatar_getter)
    titles_html = await _render_user_titles(
        result.user_titles, template_dir, avatar_getter
    )
    quotes_html = await _render_quotes(
        result.golden_quotes, template_dir, avatar_getter
    )
    chart_html = _render_activity_chart(
        stats.activity_visualization.hourly_activity, template_dir
    )
    quality_html = await _render_chat_quality(result.chat_quality, template_dir)

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
        template_dir, "image_template.html.jinja2", render_data
    )


# ══════════════════════════════════════════════════════════
#  子模板渲染
# ══════════════════════════════════════════════════════════


async def _render_topics(
    topics: list[SummaryTopic],
    template_dir: Path,
    avatar_getter: AvatarGetter | None,
) -> str:
    if not topics:
        return ""
    items: list[dict[str, Any]] = []
    for i, t in enumerate(topics):
        detail = await _render_mentions(t.detail, avatar_getter)
        items.append(
            {
                "index": i + 1,
                "topic": t.topic,
                "contributors": t.contributors,
                "contributor_ids": t.contributor_ids,
                "detail": detail,
            }
        )
    return _render_sub_template(template_dir, "topic_item.html.jinja2", topics=items)


async def _render_user_titles(
    titles: list[UserTitle],
    template_dir: Path,
    avatar_getter: AvatarGetter | None,
) -> str:
    if not titles:
        return ""
    manifest = _load_profile_manifest()
    mode = config.render.profile_display_mode

    items: list[dict[str, Any]] = []
    for u in titles:
        avatar_data = await _get_avatar_data_uri(u.user_id, avatar_getter)
        profile = _resolve_profile(manifest, mode, u.mbti)
        items.append(
            {
                "name": u.name,
                "user_id": u.user_id,
                "title": u.title,
                "mbti": u.mbti,
                "reason": u.reason,
                "avatar_data": avatar_data,
                "profile_code": profile.get("code", u.mbti),
                "profile_name": profile.get("name_zh", u.mbti),
                "profile_image": profile.get("image", ""),
            }
        )
    return _render_sub_template(
        template_dir, "user_title_item.html.jinja2", titles=items
    )


async def _render_quotes(
    quotes: list[GoldenQuote],
    template_dir: Path,
    avatar_getter: AvatarGetter | None,
) -> str:
    if not quotes:
        return ""
    items: list[dict[str, Any]] = []
    for q in quotes:
        avatar_data = (
            await _get_avatar_data_uri(q.user_id, avatar_getter) if q.user_id else ""
        )
        reason = await _render_mentions(q.reason, avatar_getter)
        items.append(
            {
                "content": q.content,
                "sender": q.sender,
                "reason": reason,
                "avatar_data": avatar_data,
            }
        )
    return _render_sub_template(template_dir, "quote_item.html.jinja2", quotes=items)


def _render_activity_chart(hourly_activity: dict[int, int], template_dir: Path) -> str:
    if not hourly_activity:
        return ""
    hours = list(range(24))
    counts = [hourly_activity.get(h, 0) for h in hours]
    return _render_sub_template(
        template_dir,
        "activity_chart.html.jinja2",
        hours=hours,
        counts=counts,
        max_count=max(counts) if counts else 1,
    )


async def _render_chat_quality(
    quality: QualityReview | None, template_dir: Path
) -> str:
    if not quality:
        return ""
    return _render_sub_template(
        template_dir, "chat_quality_item.html.jinja2", quality=quality
    )


# ══════════════════════════════════════════════════════════
#  Jinja2 渲染
# ══════════════════════════════════════════════════════════


def _get_jinja_env(template_dir: Path) -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=jinja2.select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _render_sub_template(template_dir: Path, template_name: str, **kwargs: Any) -> str:
    try:
        env = _get_jinja_env(template_dir)
        return env.get_template(template_name).render(**kwargs)
    except Exception as e:
        logger.warning(f"子模板渲染失败 ({template_name}): {escape_tag(str(e))}")
        return ""


async def _render_to_image(
    template_dir: Path, template_name: str, render_data: dict[str, Any]
) -> bytes | None:
    try:
        env = _get_jinja_env(template_dir)
        html = env.get_template(template_name).render(**render_data)

        scale = config.render.device_scale_factor
        timeout = config.render.render_timeout

        async with get_new_page(
            viewport={"width": 800, "height": 2000},
            device_scale_factor=scale,
        ) as page:
            await page.set_content(html, wait_until="networkidle")
            await page.wait_for_timeout(min(timeout, 5000))
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 800, "height": height + 50})
            container = await page.query_selector("#report-container")
            if container:
                return await container.screenshot(type="png")
            return await page.screenshot(full_page=True, type="png")

    except Exception as e:
        logger.opt(colors=True).error(f"图片渲染失败: {escape_tag(str(e))}")
        return None


# ══════════════════════════════════════════════════════════
#  头像 & 工具函数
# ══════════════════════════════════════════════════════════


async def _get_avatar_data_uri(
    uid: str,
    avatar_getter: AvatarGetter | None,
) -> str:
    """通过 avatar_getter 获取头像 URL，下载并转为 base64 Data URI。"""
    if not uid or uid == "0" or not avatar_getter:
        return ""

    url = await avatar_getter(uid)
    if not url:
        return ""

    # 从缓存读取
    if cached := await _avatar_cache.get(url):
        return cached

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                b64 = base64.b64encode(resp.content).decode()
                content_type = resp.headers.get("content-type", "image/png")
                uri = f"data:{content_type};base64,{b64}"
                await _avatar_cache.set(url, uri, ttl=24 * 3600)
                return uri
    except Exception as e:
        logger.debug(f"头像下载失败 ({uid}): {escape_tag(str(e))}")
    return ""


async def _render_mentions(text: str, avatar_getter: AvatarGetter | None) -> str:
    """将 [123456] 格式的用户引用替换为带头像的 HTML 胶囊。"""
    if not avatar_getter:
        return text

    uids = re.findall(r"\[(\d+)\]", text)
    if not uids:
        return text

    # 预取头像 URL 并下载
    avatar_map: dict[str, str] = {}
    for uid in set(uids):
        uri = await _get_avatar_data_uri(uid, avatar_getter)
        if uri:
            avatar_map[uid] = uri

    def _replace(m: re.Match[str]) -> str:
        uid = m.group(1)
        src = avatar_map.get(uid, "")
        img = f'<img class="mention-avatar" src="{src}" />' if src else ""
        return f'<span class="mention" data-uid="{uid}">{img}@{uid}</span>'

    return re.sub(r"\[(\d+)\]", _replace, text)


def _load_profile_manifest() -> dict[str, Any]:
    try:
        return json.loads(PROFILE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _resolve_profile(manifest: dict[str, Any], mode: str, mbti: str) -> dict[str, str]:
    if not mbti:
        return {}
    mode_data = manifest.get(mode, manifest.get("mbti", {}))
    return mode_data.get(mbti.upper(), {})
