from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ....http_transport import ValidatedHttpTarget


@dataclass(frozen=True, slots=True)
class DownloadedPage:
    status_code: int
    final_url: str
    media_type: str | None
    charset: str | None
    body: bytes


@dataclass(frozen=True, slots=True)
class DownloadedSourceMedia:
    page: int
    media_type: str
    body: bytes
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.page <= 0:
            raise ValueError("source media page must be positive")
        if not self.media_type.strip():
            raise ValueError("source media type must not be empty")
        if not self.body:
            raise ValueError("source media body must not be empty")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("source media dimensions must be positive")


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    title: str
    author: str | None
    site: str | None
    published: str | None
    language: str | None
    text: str


@dataclass(frozen=True, slots=True)
class SourceTarget:
    source_id: str
    canonical_url: str
    value: Any


@dataclass(frozen=True, slots=True)
class SpecializedPage:
    final_url: str
    extracted: ExtractedPage
    media_count: int = 0
    media_restricted: bool = False

    def __post_init__(self) -> None:
        if self.media_count < 0:
            raise ValueError("specialized page media count must not be negative")
        if self.media_restricted and self.media_count == 0:
            raise ValueError("restricted media requires a positive media count")


class SourceAdapterError(RuntimeError):
    """A source adapter rejected or could not parse a provider response."""


class SourceIO(Protocol):
    @property
    def respect_robots(self) -> bool: ...

    @property
    def max_redirects(self) -> int: ...

    async def download(
        self,
        url: str,
        *,
        accept: str,
        allowed_content_types: Sequence[str],
    ) -> DownloadedPage: ...

    async def download_media(
        self,
        url: str,
        *,
        referer: str,
        allowed_hosts: frozenset[str],
        max_bytes: int,
    ) -> DownloadedPage: ...

    async def resolve_redirects(
        self,
        url: str,
        *,
        allowed_hosts: frozenset[str],
    ) -> str | None: ...


class SourceAdapter(Protocol):
    source_id: str

    def recognize(self, target: ValidatedHttpTarget) -> SourceTarget | None: ...

    async def fetch_specialized(
        self,
        target: SourceTarget,
        io: SourceIO,
    ) -> SpecializedPage | None: ...

    def extract_html(
        self,
        *,
        html: str,
        final_url: str,
    ) -> ExtractedPage | None: ...

    async def resolve_card_url(self, url: str, io: SourceIO) -> str | None: ...

    async def fetch_media(
        self,
        target: SourceTarget,
        pages: Sequence[int],
        io: SourceIO,
        *,
        max_bytes: int,
    ) -> tuple[DownloadedSourceMedia, ...]: ...


__all__ = [
    "DownloadedPage",
    "DownloadedSourceMedia",
    "ExtractedPage",
    "SourceAdapter",
    "SourceAdapterError",
    "SourceIO",
    "SourceTarget",
    "SpecializedPage",
]
