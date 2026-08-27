from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from .contracts import (
    DownloadedSourceMedia,
    ExtractedPage,
    SourceIO,
    SourceTarget,
    SpecializedPage,
    ValidatedTarget,
)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_page_text(value: str) -> str:
    value = _CONTROL_RE.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in value.split("\n")]
    normalized: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            normalized.append(line)
            blank = False
        elif normalized and not blank:
            normalized.append("")
            blank = True
    while normalized and not normalized[-1]:
        normalized.pop()
    return "\n".join(normalized).strip()


def normalize_single_line(value: str, maximum: int) -> str:
    value = _CONTROL_RE.sub("", value)
    value = " ".join(value.split())
    return value[:maximum].strip()


def optional_metadata(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return normalize_single_line(value, maximum) or None


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
