from collections.abc import Sequence

from ..text import normalize_page_text, normalize_single_line, optional_metadata
from .contracts import (
    DownloadedSourceMedia,
    ExtractedPage,
    SourceIO,
    SourceTarget,
    SpecializedPage,
    ValidatedTarget,
)


class BaseSourceAdapter:
    source_id = "unknown"

    def recognize(self, target: ValidatedTarget) -> SourceTarget | None:
        _ = target
        return None

    async def fetch_specialized(
        self,
        target: SourceTarget,
        io: SourceIO,
    ) -> SpecializedPage | None:
        _ = target, io
        return None

    def extract_html(
        self,
        *,
        html: str,
        final_url: str,
    ) -> ExtractedPage | None:
        _ = html, final_url
        return None

    async def resolve_card_url(self, url: str, io: SourceIO) -> str | None:
        _ = url, io
        return None

    async def fetch_media(
        self,
        target: SourceTarget,
        pages: Sequence[int],
        io: SourceIO,
        *,
        max_bytes: int,
    ) -> tuple[DownloadedSourceMedia, ...]:
        _ = target, pages, io, max_bytes
        return ()


__all__ = [
    "BaseSourceAdapter",
    "normalize_page_text",
    "normalize_single_line",
    "optional_metadata",
]
