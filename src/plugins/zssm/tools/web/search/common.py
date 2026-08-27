import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from ....contracts import (
    CitationRegistry,
    CitationSourceKind,
    SearchResult,
    WebSearchResult,
)
from ..text import normalize_single_line
from ..urls import InvalidWebUrlError, normalize_http_url

_CAUSE_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")
_MAX_URL_CHARS = 4096

type SearchErrorCode = Literal[
    "configuration",
    "invalid_response",
    "rate_limited",
    "timeout",
    "unavailable",
]


type SearchDiagnosticReason = Literal[
    "forbidden",
    "feature_not_available",
    "inactive_api_key",
    "invalid_api_key",
    "no_results",
    "request_blocked",
    "usage_limit",
]


class WebSearchError(RuntimeError):
    """A provider failure with only stable, non-sensitive diagnostic facts."""

    def __init__(
        self,
        code: SearchErrorCode,
        *,
        cause_type: str | None = None,
        status_code: int | None = None,
        reason: SearchDiagnosticReason | None = None,
    ) -> None:
        if cause_type is not None and not _CAUSE_TYPE_RE.fullmatch(cause_type):
            raise ValueError("web search cause type is invalid")
        if status_code is not None and not 100 <= status_code <= 599:
            raise ValueError("web search status code is invalid")
        self.code = code
        self.cause_type = cause_type
        self.status_code = status_code
        self.reason = reason
        super().__init__(code)


def normalize_search_rows(
    *,
    query: str,
    rows: Sequence[Any],
    max_results: int,
    citations: CitationRegistry,
    url_fields: Sequence[str],
    snippet_fields: Sequence[str],
    source_fields: Sequence[str],
    published_fields: Sequence[str],
) -> WebSearchResult:
    normalized: list[SearchResult] = []
    seen_urls: set[str] = set()
    truncated = len(rows) > max_results
    for raw in rows:
        if len(normalized) >= max_results:
            truncated = True
            break
        if not isinstance(raw, Mapping):
            continue
        try:
            title = _required_field(raw, ("title", "name"), maximum=500)
            url = normalize_http_url(
                _required_field(raw, url_fields, maximum=_MAX_URL_CHARS)
            )
            if url in seen_urls:
                continue
            snippet = _optional_field(raw, snippet_fields, maximum=2000) or ""
            source = _optional_field(
                raw, source_fields, maximum=300
            ) or _source_from_url(url)
            published = _optional_field(raw, published_fields, maximum=200)
            language = _optional_field(raw, ("language", "lang"), maximum=50)
            citation = citations.register(
                source_kind=CitationSourceKind.SEARCH,
                title=title,
                url=url,
                source=source,
                published=published,
            )
        except TypeError, ValueError, InvalidWebUrlError:
            continue
        seen_urls.add(url)
        normalized.append(
            SearchResult(
                rank=len(normalized) + 1,
                title=title,
                url=url,
                snippet=snippet,
                source=source,
                published=published,
                language=language,
                citation_id=citation.citation_id,
            )
        )
    return WebSearchResult(query=query, results=tuple(normalized), truncated=truncated)


def _required_field(
    row: Mapping[str, Any],
    names: Sequence[str],
    *,
    maximum: int,
) -> str:
    value = _optional_field(row, names, maximum=maximum)
    if value is None:
        raise ValueError
    return value


def _optional_field(
    row: Mapping[str, Any],
    names: Sequence[str],
    *,
    maximum: int,
) -> str | None:
    for name in names:
        value = row.get(name)
        if isinstance(value, str):
            normalized = normalize_single_line(value, maximum)
            if normalized:
                return normalized
        elif isinstance(value, Mapping):
            for nested_name in ("long_name", "name"):
                nested = value.get(nested_name)
                if isinstance(nested, str):
                    normalized = normalize_single_line(nested, maximum)
                    if normalized:
                        return normalized
    return None


def _source_from_url(url: str) -> str:
    return cast("str", urlsplit(url).hostname)


__all__ = [
    "SearchDiagnosticReason",
    "SearchErrorCode",
    "WebSearchError",
    "normalize_search_rows",
]
