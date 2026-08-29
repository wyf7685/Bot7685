import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from ._validation import _citation_id, _http_url, _nonempty, _sha256

_MEDIA_ID_RE = re.compile(r"^m[1-9][0-9]*$")


class CitationSourceKind(StrEnum):
    SEARCH = "search"
    PAGE = "page"


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    source_kind: CitationSourceKind
    title: str
    url: str
    source: str | None = None
    published: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        for name in ("source", "published"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


class CitationRegistry(Protocol):
    """Register normalized targets and allocate stable s1... IDs."""

    def register(
        self,
        *,
        source_kind: CitationSourceKind,
        title: str,
        url: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation: ...
    def get(self, citation_id: str) -> Citation | None: ...
    def mark_used(self, citation_id: str) -> bool: ...
    def used_citations(self) -> tuple[Citation, ...]: ...


@dataclass(frozen=True, slots=True)
class SearchResult:
    rank: int
    title: str
    url: str
    snippet: str
    source: str | None
    published: str | None
    language: str | None
    citation_id: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError("rank must be positive")
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        object.__setattr__(self, "snippet", self.snippet.strip())
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        for name in ("source", "published", "language"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    query: str
    results: tuple[SearchResult, ...]
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _nonempty(self.query, "query"))
        object.__setattr__(self, "results", tuple(self.results))
        if tuple(item.rank for item in self.results) != tuple(
            range(1, len(self.results) + 1)
        ):
            raise ValueError("search result ranks must be contiguous and ordered")
        ids = tuple(item.citation_id for item in self.results)
        if len(set(ids)) != len(ids):
            raise ValueError("search results must not repeat citation IDs")

    @property
    def returned(self) -> int:
        return len(self.results)


@dataclass(frozen=True, slots=True)
class MediaSetRef:
    media_id: str
    count: int
    restricted: bool = False

    def __post_init__(self) -> None:
        media_id = self.media_id.strip()
        if not _MEDIA_ID_RE.fullmatch(media_id):
            raise ValueError("media_id must match m<positive integer>")
        if self.count <= 0:
            raise ValueError("media count must be positive")
        object.__setattr__(self, "media_id", media_id)


@dataclass(frozen=True, slots=True)
class WebPageResult:
    title: str
    author: str | None
    site: str | None
    published: str | None
    language: str | None
    text: str
    truncated: bool
    final_url: str
    content_sha256: str
    citation_id: str
    media: MediaSetRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "text", _nonempty(self.text, "text"))
        object.__setattr__(self, "final_url", _http_url(self.final_url, "final_url"))
        object.__setattr__(self, "content_sha256", _sha256(self.content_sha256))
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        if self.media is not None and not isinstance(self.media, MediaSetRef):
            raise TypeError("page media must be a MediaSetRef")
        for name in ("author", "site", "published", "language"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


SearchFreshness = Literal["any", "day", "week", "month", "year"]


class WebSearchProvider(Protocol):
    """A configured invocation-bound provider; credentials remain inside it."""

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult: ...


class SafePageFetcher(Protocol):
    """An invocation-bound SSRF-safe fetcher with policy already configured."""

    async def fetch(self, url: str) -> WebPageResult: ...


__all__ = [
    "Citation",
    "CitationRegistry",
    "CitationSourceKind",
    "MediaSetRef",
    "SafePageFetcher",
    "SearchFreshness",
    "SearchResult",
    "WebPageResult",
    "WebSearchProvider",
    "WebSearchResult",
]
