import json
import re
from collections.abc import Callable, Mapping, Sequence
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

from .base import (
    BaseSourceAdapter,
    normalize_page_text,
    normalize_single_line,
    optional_metadata,
)
from .contracts import (
    DownloadedSourceMedia,
    ExtractedPage,
    SourceAdapterError,
    SourceIO,
    SourceTarget,
    SpecializedPage,
    ValidatedTarget,
)

_PIXIV_HOSTS = frozenset({"pixiv.net", "www.pixiv.net"})
_PIXIV_ARTWORK_PATH_RE = re.compile(
    r"^/(?:en/)?artworks/(?P<artwork_id>[1-9][0-9]{0,19})/?$"
)
_PIXIV_SHORT_PATH_RE = re.compile(r"^/i/(?P<artwork_id>[1-9][0-9]{0,19})/?$")
_PIXIV_LEGACY_PATH = "/member_illust.php"
_PIXIV_AJAX_ORIGIN = "https://www.pixiv.net"
_PIXIV_OEMBED_ENDPOINT = "https://embed.pixiv.net/oembed.php"
_PIXIV_IMAGE_HOSTS = frozenset({"i.pximg.net"})
_PIXIV_REFERER = "https://www.pixiv.net/"
_MAX_CAPTION_HTML_CHARS = 32_000
_MAX_CAPTION_CHARS = 4_000
_MAX_TAGS = 16
_MAX_TAG_CHARS = 96

_WORK_TYPE_LABELS = {
    0: "插画",
    1: "漫画",
    2: "动图",
}
_CONTENT_RATING_LABELS = {
    0: "全年龄",
    1: "R-18",
    2: "R-18G",
}
_BLOCK_TAGS = frozenset(
    {
        "blockquote",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "section",
        "ul",
    }
)
_IGNORED_TAGS = frozenset({"script", "style"})


class _CaptionHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        _ = attrs
        normalized = tag.casefold()
        if normalized in _IGNORED_TAGS:
            self._ignored_depth += 1
        elif self._ignored_depth == 0 and (
            normalized == "br" or normalized in _BLOCK_TAGS
        ):
            self._parts.append("\n")

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if tag.casefold() in _IGNORED_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if normalized in _IGNORED_TAGS:
            if self._ignored_depth > 0:
                self._ignored_depth -= 1
        elif self._ignored_depth == 0 and normalized in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


class PixivAdapter(BaseSourceAdapter):
    source_id = "pixiv"

    def recognize(self, target: ValidatedTarget) -> SourceTarget | None:
        canonical = canonical_pixiv_artwork_url(target.url)
        if canonical is None:
            return None
        artwork_id = urlsplit(canonical).path.rsplit("/", 1)[-1]
        return SourceTarget(self.source_id, canonical, artwork_id)

    async def fetch_specialized(
        self,
        target: SourceTarget,
        io: SourceIO,
    ) -> SpecializedPage | None:
        artwork_id = target.value
        if not isinstance(artwork_id, str):
            return None

        candidates: tuple[
            tuple[str, Callable[[Mapping[str, Any]], ExtractedPage], bool], ...
        ] = (
            (
                f"{_PIXIV_AJAX_ORIGIN}/ajax/illust/{artwork_id}?lang=zh",
                parse_pixiv_ajax_payload,
                True,
            ),
            (
                f"{_PIXIV_OEMBED_ENDPOINT}?{urlencode({"url": target.canonical_url})}",
                parse_pixiv_oembed_payload,
                False,
            ),
        )
        last_error: Exception | None = None
        for api_url, parser, includes_media in candidates:
            try:
                downloaded = await io.download(
                    api_url,
                    accept="application/json",
                    allowed_content_types=("application/json",),
                )
                payload = decode_pixiv_json(downloaded.body, downloaded.charset)
                extracted = parser(payload)
                media_count = pixiv_media_count(payload) if includes_media else 0
                restricted = pixiv_media_restricted(payload) if media_count else False
                return SpecializedPage(
                    target.canonical_url,
                    extracted,
                    media_count=media_count,
                    media_restricted=restricted,
                )
            except Exception as error:
                last_error = error
        if last_error is not None:
            raise last_error
        return None

    async def resolve_card_url(self, url: str, io: SourceIO) -> str | None:
        _ = io
        return canonical_pixiv_artwork_url(url)

    async def fetch_media(
        self,
        target: SourceTarget,
        pages: Sequence[int],
        io: SourceIO,
        *,
        max_bytes: int,
    ) -> tuple[DownloadedSourceMedia, ...]:
        artwork_id = target.value
        if not isinstance(artwork_id, str):
            raise SourceAdapterError("pixiv media target is invalid")
        downloaded = await io.download(
            f"{_PIXIV_AJAX_ORIGIN}/ajax/illust/{artwork_id}/pages?lang=zh",
            accept="application/json",
            allowed_content_types=("application/json",),
        )
        payload = decode_pixiv_json(downloaded.body, downloaded.charset)
        media_pages = parse_pixiv_media_pages(payload)
        results: list[DownloadedSourceMedia] = []
        for page in pages:
            if page <= 0 or page > len(media_pages):
                raise SourceAdapterError("pixiv media page is out of range")
            item = media_pages[page - 1]
            image = await io.download_media(
                item[0],
                referer=_PIXIV_REFERER,
                allowed_hosts=_PIXIV_IMAGE_HOSTS,
                max_bytes=max_bytes,
            )
            if image.media_type is None:
                raise SourceAdapterError("pixiv image response has no media type")
            results.append(
                DownloadedSourceMedia(
                    page=page,
                    media_type=image.media_type,
                    body=image.body,
                    width=item[1],
                    height=item[2],
                )
            )
        return tuple(results)


def canonical_pixiv_artwork_url(url: str) -> str | None:
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname.casefold() if parsed.hostname is not None else None
        port = parsed.port
    except UnicodeError, ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or hostname not in _PIXIV_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port
        not in (
            None,
            80 if parsed.scheme.casefold() == "http" else 443,
        )
    ):
        return None

    artwork_id: str | None = None
    for pattern in (_PIXIV_ARTWORK_PATH_RE, _PIXIV_SHORT_PATH_RE):
        if match := pattern.fullmatch(parsed.path):
            artwork_id = match.group("artwork_id")
            break
    if artwork_id is None and parsed.path == _PIXIV_LEGACY_PATH:
        query = parse_qs(parsed.query, keep_blank_values=True)
        values = query.get("illust_id", [])
        if len(values) == 1 and re.fullmatch(r"[1-9][0-9]{0,19}", values[0]):
            artwork_id = values[0]
    if artwork_id is None:
        return None
    return f"https://www.pixiv.net/artworks/{artwork_id}"


def decode_pixiv_json(body: bytes, charset: str | None) -> Mapping[str, Any]:
    encoding = charset or "utf-8"
    try:
        payload = json.loads(body.decode(encoding, errors="replace").lstrip("\ufeff"))
    except UnicodeError, json.JSONDecodeError:
        raise SourceAdapterError("pixiv response is not valid JSON") from None
    if not isinstance(payload, Mapping):
        raise SourceAdapterError("pixiv response must be an object")
    return payload


def parse_pixiv_json(
    body: bytes,
    charset: str | None,
    parser: Callable[[Mapping[str, Any]], ExtractedPage],
) -> ExtractedPage:
    return parser(decode_pixiv_json(body, charset))


def parse_pixiv_ajax_payload(payload: Mapping[str, Any]) -> ExtractedPage:
    body = _pixiv_ajax_body(payload)

    title = optional_metadata(body.get("title") or body.get("illustTitle"), 500)
    if title is None:
        raise SourceAdapterError("pixiv API response has no title")
    author = optional_metadata(body.get("userName"), 300)
    published = optional_metadata(
        body.get("createDate") or body.get("uploadDate"),
        100,
    )
    description = pixiv_caption_text(
        body.get("description") or body.get("illustComment")
    )

    lines = [f"标题：{title}"]
    if author:
        lines.append(f"作者：{author}")
    if work_type := _work_type_label(body.get("illustType")):
        lines.append(f"作品类型：{work_type}")
    if published:
        lines.append(f"发布时间：{published}")

    specification = _pixiv_specification(body)
    if specification:
        lines.append(f"规格：{specification}")
    if description and description != title:
        lines.append(f"简介：{description}")
    if tags := pixiv_tags(body.get("tags")):
        lines.append(f"标签：{"、".join(tags)}")
    if metrics := _pixiv_metrics(body):
        lines.append(f"互动数据：{metrics}")
    if rating := _content_rating_label(body.get("xRestrict")):
        lines.append(f"内容分级：{rating}")
    if body.get("aiType") == 2:
        lines.append("AI 标记：AI 生成")
    if body.get("isLoginOnly") is True:
        lines.append("可见范围：登录后可见")
    if body.get("isMasked") is True:
        lines.append("状态：内容已遮罩")
    lines.append("说明：以上为作品元数据，不包含画面识别结果。")

    return ExtractedPage(
        title=title,
        author=author,
        site="pixiv",
        published=published,
        language=None,
        text=normalize_page_text("\n".join(lines)),
    )


def pixiv_media_count(payload: Mapping[str, Any]) -> int:
    body = _pixiv_ajax_body(payload)
    return _positive_int(body.get("pageCount")) or 0


def pixiv_media_restricted(payload: Mapping[str, Any]) -> bool:
    body = _pixiv_ajax_body(payload)
    return (
        body.get("xRestrict") in {1, 2}
        or body.get("isLoginOnly") is True
        or body.get("isMasked") is True
        or body.get("isUnlisted") is True
    )


def parse_pixiv_media_pages(
    payload: Mapping[str, Any],
) -> tuple[tuple[str, int, int], ...]:
    if payload.get("error") is not False:
        raise SourceAdapterError("pixiv pages API returned an error")
    body = payload.get("body")
    if not isinstance(body, Sequence) or isinstance(body, str):
        raise SourceAdapterError("pixiv pages API response has no page list")
    pages: list[tuple[str, int, int]] = []
    for item in body:
        if not isinstance(item, Mapping):
            raise SourceAdapterError("pixiv pages API contains an invalid page")
        urls = item.get("urls")
        raw_url = urls.get("regular") if isinstance(urls, Mapping) else None
        width = _positive_int(item.get("width"))
        height = _positive_int(item.get("height"))
        if not isinstance(raw_url, str) or width is None or height is None:
            raise SourceAdapterError("pixiv page metadata is incomplete")
        try:
            parsed = urlsplit(raw_url)
            port = parsed.port
        except UnicodeError, ValueError:
            raise SourceAdapterError("pixiv image URL is invalid") from None
        if (
            parsed.scheme.casefold() != "https"
            or parsed.hostname is None
            or parsed.hostname.casefold().rstrip(".") not in _PIXIV_IMAGE_HOSTS
            or port not in (None, 443)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise SourceAdapterError("pixiv image URL is invalid")
        pages.append((raw_url, width, height))
    if not pages:
        raise SourceAdapterError("pixiv pages API returned no pages")
    return tuple(pages)


def _pixiv_ajax_body(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if payload.get("error") is not False:
        raise SourceAdapterError("pixiv API returned an error")
    body = payload.get("body")
    if not isinstance(body, Mapping):
        raise SourceAdapterError("pixiv API response has no body")
    return body


def parse_pixiv_oembed_payload(payload: Mapping[str, Any]) -> ExtractedPage:
    title = optional_metadata(payload.get("title"), 500)
    if title is None:
        raise SourceAdapterError("pixiv oEmbed response has no title")
    author = optional_metadata(payload.get("author_name"), 300)
    work_type = optional_metadata(payload.get("work_type"), 50)

    lines = [f"标题：{title}"]
    if author:
        lines.append(f"作者：{author}")
    if work_type:
        lines.append(f"作品类型：{_oembed_work_type_label(work_type)}")
    lines.append("说明：仅提取到基础作品元数据，不包含作品简介或画面识别结果。")
    return ExtractedPage(
        title=title,
        author=author,
        site="pixiv",
        published=None,
        language=None,
        text=normalize_page_text("\n".join(lines)),
    )


def pixiv_caption_text(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    parser = _CaptionHTMLParser()
    try:
        parser.feed(value[:_MAX_CAPTION_HTML_CHARS])
        parser.close()
    except Exception:
        return ""
    text = normalize_page_text(parser.text())
    return normalize_page_text(text[:_MAX_CAPTION_CHARS])


def pixiv_tags(value: Any) -> tuple[str, ...]:
    if not isinstance(value, Mapping):
        return ()
    raw_tags = value.get("tags")
    if not isinstance(raw_tags, Sequence) or isinstance(raw_tags, str):
        return ()

    tags: list[str] = []
    seen: set[str] = set()
    for item in raw_tags:
        if not isinstance(item, Mapping):
            continue
        tag = optional_metadata(item.get("tag"), _MAX_TAG_CHARS)
        if tag is None or tag in seen:
            continue
        seen.add(tag)
        translation = _tag_translation(item.get("translation"), tag)
        tags.append(f"{tag}（{translation}）" if translation else tag)
        if len(tags) >= _MAX_TAGS:
            break
    return tuple(tags)


def _tag_translation(value: Any, original: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    for language in ("zh", "zh-cn", "zh_tw", "zh-tw", "en"):
        translated = optional_metadata(value.get(language), _MAX_TAG_CHARS)
        if translated and translated.casefold() != original.casefold():
            return translated
    return None


def _work_type_label(value: Any) -> str | None:
    return (
        _WORK_TYPE_LABELS.get(value)
        if isinstance(value, int) and not isinstance(value, bool)
        else None
    )


def _content_rating_label(value: Any) -> str | None:
    return (
        _CONTENT_RATING_LABELS.get(value)
        if isinstance(value, int) and not isinstance(value, bool)
        else None
    )


def _oembed_work_type_label(value: str) -> str:
    labels = {
        "illust": "插画",
        "manga": "漫画",
        "ugoira": "动图",
    }
    return labels.get(value.casefold(), normalize_single_line(value, 50))


def _positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _pixiv_specification(body: Mapping[str, Any]) -> str | None:
    width = _positive_int(body.get("width"))
    height = _positive_int(body.get("height"))
    page_count = _positive_int(body.get("pageCount"))
    parts: list[str] = []
    if width is not None and height is not None:
        parts.append(f"{width}×{height}")
    if page_count is not None:
        parts.append(f"共 {page_count} 页")
    return "，".join(parts) or None


def _pixiv_metrics(body: Mapping[str, Any]) -> str | None:
    labels = (
        ("viewCount", "浏览"),
        ("bookmarkCount", "收藏"),
        ("likeCount", "点赞"),
        ("commentCount", "评论"),
    )
    values = [
        f"{label}={value}"
        for key, label in labels
        if (value := _nonnegative_int(body.get(key))) is not None
    ]
    return "，".join(values) or None


__all__ = [
    "PixivAdapter",
    "canonical_pixiv_artwork_url",
    "parse_pixiv_ajax_payload",
    "parse_pixiv_oembed_payload",
    "pixiv_caption_text",
    "pixiv_tags",
]
