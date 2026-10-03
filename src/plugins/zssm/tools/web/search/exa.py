from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta

import httpx2

from ....config import WebSearchConfig
from ....contracts.web import (
    CitationRegistry,
    SearchFreshness,
    WebSearchProvider,
    WebSearchResult,
)
from .common import WebSearchError, normalize_search_rows

_EXA_ENDPOINT = "https://api.exa.ai/search"
_EXA_MAX_SNIPPET_CHARS = 2000
_FRESHNESS_LOOKBACK_DAYS: dict[SearchFreshness, int] = {
    "day": 1,
    "week": 7,
    "month": 30,
    "year": 365,
}


def _freshness_start_date(
    freshness: SearchFreshness, *, today_utc: date | None = None
) -> str | None:
    """Return a UTC publication-date threshold; month/year are 30/365 days."""
    if freshness == "any":
        return None
    today = today_utc or datetime.now(UTC).date()
    return (today - timedelta(days=_FRESHNESS_LOOKBACK_DAYS[freshness])).isoformat()


class ExaSearchProvider(WebSearchProvider):
    """Exa search using an application-owned shared HTTP client."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
        client: httpx2.AsyncClient,
    ) -> None:
        if config.backend != "exa" or config.exa_api_key is None:
            raise ValueError("ExaSearchProvider requires configured Exa credentials")
        self._client = client
        self._api_key = config.exa_api_key
        self._timeout = httpx2.Timeout(config.timeout_seconds)
        # Exa exposes one moderation boolean, with no separate strict setting.
        self._moderation = config.safe_search != "off"
        self._citations = citation_registry

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult:
        body: dict[str, object] = {
            "query": query,
            "numResults": max_results + 1,
            "moderation": self._moderation,
            "contents": {"text": {"maxCharacters": _EXA_MAX_SNIPPET_CHARS}},
        }
        if (start_date := _freshness_start_date(freshness)) is not None:
            body["startPublishedDate"] = start_date
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "x-api-key": self._api_key.get_secret_value(),
        }
        try:
            response = await self._client.post(
                _EXA_ENDPOINT,
                json=body,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx2.TimeoutException as error:
            error.add_note("stage=web_search operation=provider_request")
            raise WebSearchError("timeout", cause_type=type(error).__name__) from error
        except httpx2.HTTPError as error:
            error.add_note("stage=web_search operation=provider_request")
            raise WebSearchError(
                "unavailable", cause_type=type(error).__name__
            ) from error

        if response.status_code == 429:
            raise WebSearchError("rate_limited", status_code=response.status_code)
        if response.status_code in (401, 403):
            raise WebSearchError("configuration", status_code=response.status_code)
        if not 200 <= response.status_code < 300:
            raise WebSearchError("unavailable", status_code=response.status_code)

        try:
            payload = response.json()
            if not isinstance(payload, Mapping):
                raise TypeError
            rows = payload.get("results")
            if not isinstance(rows, list):
                raise TypeError
            return normalize_search_rows(
                query=query,
                rows=rows,
                max_results=max_results,
                citations=self._citations,
                url_fields=("url",),
                snippet_fields=("text", "snippet", "description"),
                source_fields=(),
                published_fields=("publishedDate",),
            )
        except (TypeError, ValueError) as error:
            error.add_note("stage=web_search operation=response_parse")
            raise WebSearchError(
                "invalid_response", cause_type=type(error).__name__
            ) from error


__all__ = ["ExaSearchProvider"]
