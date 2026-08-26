from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlsplit

from .base import (
    BaseSourceAdapter,
    normalize_page_text,
    normalize_single_line,
    optional_metadata,
)
from .contracts import (
    ExtractedPage,
    SourceAdapterError,
    SourceIO,
    SourceTarget,
    SpecializedPage,
    ValidatedTarget,
)

_TWITTER_HOSTS = frozenset(
    {
        "x.com",
        "mobile.x.com",
        "www.x.com",
        "twitter.com",
        "mobile.twitter.com",
        "www.twitter.com",
    }
)
_FXTWITTER_API_ORIGIN = "https://api.fxtwitter.com"
_VXTWITTER_API_ORIGIN = "https://api.vxtwitter.com"
_TWITTER_STATUS_PATH_RE = re.compile(
    r"^/(?:(?P<screen_name>[A-Za-z0-9_]{1,15})|i/web)/status/(?P<status_id>[0-9]{2,20})(?:/.*)?/?$"
)


class TwitterAdapter(BaseSourceAdapter):
    source_id = "twitter"

    def recognize(self, target: ValidatedTarget) -> SourceTarget | None:
        if target.hostname not in _TWITTER_HOSTS:
            return None
        match = _TWITTER_STATUS_PATH_RE.fullmatch(urlsplit(target.url).path)
        if match is None:
            return None
        return SourceTarget(
            self.source_id,
            target.url,
            {
                "status_id": match.group("status_id"),
                "screen_name": match.group("screen_name"),
            },
        )

    async def fetch_specialized(
        self,
        target: SourceTarget,
        io: SourceIO,
    ) -> SpecializedPage | None:
        value = target.value
        if not isinstance(value, Mapping):
            return None
        status_id = value.get("status_id")
        screen_name = value.get("screen_name")
        if not isinstance(status_id, str):
            return None
        if not isinstance(screen_name, str):
            vxtwitter_path = f"status/{status_id}"
        else:
            vxtwitter_path = f"{screen_name}/status/{status_id}"

        candidates: tuple[tuple[str, Any], ...] = (
            (
                f"{_VXTWITTER_API_ORIGIN}/{vxtwitter_path}",
                parse_vxtwitter_payload,
            ),
            (
                f"{_FXTWITTER_API_ORIGIN}/2/status/{status_id}",
                parse_fxtwitter_payload,
            ),
        )
        last_error: Exception | None = None
        for api_url, parser in candidates:
            try:
                downloaded = await io.download(
                    api_url,
                    accept="application/json",
                    allowed_content_types=("application/json",),
                )
                extracted = parse_twitter_json(
                    downloaded.body,
                    downloaded.charset,
                    parser,
                )
                return SpecializedPage(target.canonical_url, extracted)
            except Exception as error:
                last_error = error
        if last_error is not None:
            raise last_error
        return None


def parse_twitter_json(
    body: bytes,
    charset: str | None,
    parser: Any,
) -> ExtractedPage:
    encoding = charset or "utf-8"
    try:
        payload = json.loads(body.decode(encoding, errors="replace").lstrip("\ufeff"))
    except UnicodeError, json.JSONDecodeError:
        raise SourceAdapterError("twitter response is not valid JSON") from None
    if not isinstance(payload, Mapping):
        raise SourceAdapterError("twitter response must be an object")
    code = payload.get("code")
    if isinstance(code, int) and not 200 <= code < 300:
        raise SourceAdapterError(f"twitter provider returned status {code}")
    return parser(payload)


def parse_fxtwitter_payload(payload: Mapping[str, Any]) -> ExtractedPage:
    status = payload.get("status")
    if not isinstance(status, Mapping):
        raise SourceAdapterError("FxTwitter response has no status")
    author = status.get("author")
    if not isinstance(author, Mapping):
        author = {}
    return build_twitter_extracted_page(
        text=status.get("text"),
        author_name=author.get("name"),
        screen_name=author.get("screen_name"),
        created_at=status.get("created_at"),
        language=status.get("lang"),
        media=status.get("media"),
        metrics=status,
    )


def parse_vxtwitter_payload(payload: Mapping[str, Any]) -> ExtractedPage:
    return build_twitter_extracted_page(
        text=payload.get("text"),
        author_name=payload.get("user_name"),
        screen_name=payload.get("user_screen_name"),
        created_at=payload.get("date"),
        language=payload.get("lang"),
        media=payload.get("mediaURLs"),
        metrics=payload,
    )


def build_twitter_extracted_page(
    *,
    text: Any,
    author_name: Any,
    screen_name: Any,
    created_at: Any,
    language: Any,
    media: Any,
    metrics: Mapping[str, Any],
) -> ExtractedPage:
    if not isinstance(text, str):
        raise SourceAdapterError("Twitter response has no text")
    normalized_text = normalize_page_text(text)
    if not normalized_text:
        raise SourceAdapterError("Twitter response has empty text")

    name = optional_metadata(author_name, 300)
    handle = optional_metadata(screen_name, 64)
    author = name or (f"@{handle}" if handle else None)
    title = (
        f"{name or handle} (@{handle}) on X"
        if name and handle
        else f"{author} on X"
        if author
        else "X post"
    )
    published = optional_metadata(created_at, 100)
    language_value = optional_metadata(language, 50)

    lines: list[str] = []
    if author:
        lines.append(f"作者: {author}")
    if published:
        lines.append(f"发布时间: {published}")
    lines.extend(("", normalized_text))

    metric_labels = (
        ("likes", "点赞"),
        ("reposts", "转发"),
        ("replies", "回复"),
        ("quotes", "引用"),
        ("views", "浏览"),
    )
    metric_values = [
        f"{label}={value}"
        for key, label in metric_labels
        if isinstance(value := metrics.get(key), int) and not isinstance(value, bool)
    ]
    if metric_values:
        lines.extend(("", "互动数据: " + ", ".join(metric_values)))

    media_urls = twitter_media_urls(media)
    if media_urls:
        lines.extend(("", "媒体:", *(f"- {url}" for url in media_urls)))

    return ExtractedPage(
        title=normalize_single_line(title, 500),
        author=author,
        site="X",
        published=published,
        language=language_value,
        text=normalize_page_text("\n".join(lines)),
    )


def twitter_media_urls(media: Any) -> tuple[str, ...]:
    if isinstance(media, Mapping):
        values = media.get("all") or media.get("mediaURLs")
    else:
        values = media
    if not isinstance(values, Sequence) or isinstance(values, str):
        return ()

    urls: list[str] = []
    for item in values:
        raw_url = item.get("url") if isinstance(item, Mapping) else item
        if not isinstance(raw_url, str) or not raw_url.startswith(
            ("http://", "https://")
        ):
            continue
        normalized = normalize_single_line(raw_url, 2048)
        if normalized and normalized not in urls:
            urls.append(normalized)
        if len(urls) >= 8:
            break
    return tuple(urls)


__all__ = [
    "TwitterAdapter",
    "build_twitter_extracted_page",
    "parse_fxtwitter_payload",
    "parse_vxtwitter_payload",
]
