import functools
import math
import re
from functools import partial
from typing import Any

import anyio
from anyio.to_thread import run_sync

from ....config import WebSearchConfig
from ....contracts import (
    CitationRegistry,
    SearchFreshness,
    WebSearchProvider,
    WebSearchResult,
)
from .common import SearchDiagnosticReason, WebSearchError, normalize_search_rows

_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class _DDGSBackendUnavailable(RuntimeError):
    pass


@functools.cache
def _get_ddgs_limiter(max_parallel: int) -> anyio.CapacityLimiter:
    return anyio.CapacityLimiter(max_parallel)


class DDGSSearchProvider(WebSearchProvider):
    """A lazy, bounded DDGS provider pinned to one configured backend."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
    ) -> None:
        backend = config.ddgs_backend.strip().casefold()
        if (
            backend in {"auto", "all"}
            or "," in backend
            or not _HOST_LABEL_RE.fullmatch(backend)
        ):
            raise ValueError("DDGS requires one fixed named backend")
        if config.backend != "ddgs":
            raise ValueError("DDGSSearchProvider requires the DDGS backend")
        self._backend = backend
        self._timeout = max(1, math.ceil(config.timeout_seconds))
        self._safe_search = {
            "off": "off",
            "moderate": "moderate",
            "strict": "on",
        }[config.safe_search]
        self._citations = citation_registry
        self._limiter = _get_ddgs_limiter(config.ddgs_max_parallel)

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult:
        call = partial(
            self._search_sync,
            query=query,
            max_results=max_results + 1,
            freshness=freshness,
        )
        try:
            rows = await run_sync(
                call,
                limiter=self._limiter,
                abandon_on_cancel=True,
            )
        except _DDGSBackendUnavailable as error:
            raise WebSearchError(
                "configuration", cause_type=type(error).__name__
            ) from None
        except ImportError as error:
            raise WebSearchError(
                "unavailable", cause_type=type(error).__name__
            ) from None
        except Exception as error:
            cause_type = type(error).__name__
            if cause_type == "TimeoutException":
                raise WebSearchError("timeout", cause_type=cause_type) from None
            reason: SearchDiagnosticReason | None = None
            if cause_type == "DDGSException" and str(error) == "No results found.":
                reason = "no_results"
            raise WebSearchError(
                "unavailable",
                cause_type=cause_type,
                reason=reason,
            ) from None

        try:
            return normalize_search_rows(
                query=query,
                rows=rows,
                max_results=max_results,
                citations=self._citations,
                url_fields=("href", "url"),
                snippet_fields=("body", "description", "snippet"),
                source_fields=("source",),
                published_fields=("date", "published"),
            )
        except (TypeError, ValueError) as error:
            raise WebSearchError(
                "invalid_response", cause_type=type(error).__name__
            ) from None

    def _search_sync(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> list[dict[str, Any]]:
        from ddgs.ddgs import DDGS
        from ddgs.engines import ENGINES

        if self._backend not in ENGINES.get("text", {}):
            raise _DDGSBackendUnavailable
        timelimit = {
            "any": None,
            "day": "d",
            "week": "w",
            "month": "m",
            "year": "y",
        }[freshness]
        with DDGS(timeout=self._timeout) as ddgs:
            rows = ddgs.text(
                query,
                backend=self._backend,
                max_results=max_results,
                safesearch=self._safe_search,
                timelimit=timelimit,
            )
        if not isinstance(rows, list):
            raise TypeError
        return rows


__all__ = ["DDGSSearchProvider"]
