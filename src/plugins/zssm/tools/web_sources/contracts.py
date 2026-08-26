from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True, slots=True)
class ValidatedTarget:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    origin: str
    host_header: str


@dataclass(frozen=True, slots=True)
class DownloadedPage:
    status_code: int
    final_url: str
    media_type: str | None
    charset: str | None
    body: bytes


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

    async def resolve_redirects(
        self,
        url: str,
        *,
        allowed_hosts: frozenset[str],
    ) -> str | None: ...


class SourceAdapter(Protocol):
    source_id: str

    def recognize(self, target: ValidatedTarget) -> SourceTarget | None: ...

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


__all__ = [
    "DownloadedPage",
    "ExtractedPage",
    "SourceAdapter",
    "SourceAdapterError",
    "SourceIO",
    "SourceTarget",
    "SpecializedPage",
    "ValidatedTarget",
]
