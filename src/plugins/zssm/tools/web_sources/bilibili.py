from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit

from src.plugins.zssm.tools.web_sources.base import (
    BaseSourceAdapter,
    normalize_page_text,
    normalize_single_line,
    optional_metadata,
)
from src.plugins.zssm.tools.web_sources.contracts import (
    ExtractedPage,
    SourceIO,
    SourceTarget,
    ValidatedTarget,
)

_B23_HOST = "b23.tv"
_BILIBILI_VIDEO_HOSTS = frozenset(
    {"bilibili.com", "m.bilibili.com", "www.bilibili.com"}
)
_BILIBILI_REDIRECT_HOSTS = _BILIBILI_VIDEO_HOSTS | {_B23_HOST}
_BILIBILI_VIDEO_PATH_RE = re.compile(r"^/video/(BV[0-9A-Za-z]{10,20})/?$")
_MAX_JSON_LD_CHARS = 256_000


class _JSONLDScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._active = False
        self._parts: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag.casefold() != "script":
            return
        attributes = {name.casefold(): value for name, value in attrs}
        if (attributes.get("type") or "").casefold() == "application/ld+json":
            self._active = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._active:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or not self._active:
            return
        block = "".join(self._parts).strip()
        if block and len(block) <= _MAX_JSON_LD_CHARS:
            self.blocks.append(block)
        self._active = False
        self._parts = []


class BilibiliAdapter(BaseSourceAdapter):
    source_id = "bilibili"

    def recognize(self, target: ValidatedTarget) -> SourceTarget | None:
        canonical = canonical_bilibili_video_url(target.url)
        if canonical is None:
            return None
        match = _BILIBILI_VIDEO_PATH_RE.fullmatch(urlsplit(canonical).path)
        if match is None:
            return None
        return SourceTarget(self.source_id, canonical, match.group(1))

    def extract_html(
        self,
        *,
        html: str,
        final_url: str,
    ) -> ExtractedPage | None:
        return extract_bilibili_json_ld(html, final_url)

    async def resolve_card_url(self, url: str, io: SourceIO) -> str | None:
        if canonical := canonical_bilibili_video_url(url):
            return canonical
        parsed = urlsplit(url)
        if (
            parsed.scheme.casefold() != "https"
            or parsed.hostname is None
            or parsed.hostname.casefold().rstrip(".") != _B23_HOST
        ):
            return None
        redirected = await io.resolve_redirects(
            url,
            allowed_hosts=_BILIBILI_REDIRECT_HOSTS,
        )
        return canonical_bilibili_video_url(redirected or "")


def canonical_bilibili_video_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname.casefold() if parsed.hostname is not None else None
        port = parsed.port
    except UnicodeError, ValueError:
        return None
    if (
        parsed.scheme.casefold() != "https"
        or hostname not in _BILIBILI_VIDEO_HOSTS
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    match = _BILIBILI_VIDEO_PATH_RE.fullmatch(parsed.path)
    if match is None:
        return None
    return f"https://www.bilibili.com/video/{match.group(1)}/"


def extract_bilibili_json_ld(html: str, url: str) -> ExtractedPage | None:
    if canonical_bilibili_video_url(url) is None:
        return None
    parser = _JSONLDScriptParser()
    parser.feed(html)
    video: Mapping[str, Any] | None = None
    for block in parser.blocks:
        try:
            value = json.loads(block)
        except json.JSONDecodeError:
            continue
        video = next(
            (item for item in json_ld_objects(value) if is_video_object(item)),
            None,
        )
        if video is not None:
            break
    if video is None:
        return None

    title = optional_metadata(video.get("name"), 500)
    if title is None:
        return None
    description = (
        normalize_page_text(video["description"])[:4000]
        if isinstance(video.get("description"), str)
        else ""
    )
    author_value = video.get("author")
    author = (
        optional_metadata(author_value.get("name"), 300)
        if isinstance(author_value, Mapping)
        else None
    )
    published = optional_metadata(
        video.get("datePublished") or video.get("uploadDate"),
        100,
    )
    language = optional_metadata(video.get("inLanguage"), 50)
    duration = optional_metadata(video.get("duration"), 100)
    keywords = normalize_keywords(video.get("keywords"))

    lines = [f"标题：{title}"]
    if description and description != title:
        lines.append(f"简介：{description}")
    if author:
        lines.append(f"作者：{author}")
    if published:
        lines.append(f"发布时间：{published}")
    if duration:
        lines.append(f"时长：{duration}")
    if keywords:
        lines.append(f"关键词：{"、".join(keywords)}")
    return ExtractedPage(
        title=title,
        author=author,
        site="哔哩哔哩",
        published=published,
        language=language,
        text="\n".join(lines),
    )


def json_ld_objects(value: object) -> Sequence[Mapping[str, Any]]:
    if isinstance(value, Mapping):
        objects = [value]
        graph = value.get("@graph")
        if isinstance(graph, list):
            objects.extend(item for item in graph if isinstance(item, Mapping))
        return tuple(objects)
    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def is_video_object(value: Mapping[str, Any]) -> bool:
    object_type = value.get("@type")
    return object_type == "VideoObject" or (
        isinstance(object_type, list) and "VideoObject" in object_type
    )


def normalize_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        values = value[:12]
    elif isinstance(value, str):
        values = value.split(",")[:12]
    else:
        return ()
    return tuple(
        normalized
        for item in values
        if isinstance(item, str) and (normalized := normalize_single_line(item, 64))
    )


__all__ = [
    "BilibiliAdapter",
    "canonical_bilibili_video_url",
    "extract_bilibili_json_ld",
]
