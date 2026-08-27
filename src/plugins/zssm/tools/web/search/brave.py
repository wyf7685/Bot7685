from collections.abc import Mapping
from typing import Any

import httpx

from ....config import WebSearchConfig
from ....contracts import (
    CitationRegistry,
    SearchFreshness,
    WebSearchProvider,
    WebSearchResult,
)
from .common import WebSearchError, normalize_search_rows

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(WebSearchProvider):
    """Brave web search using an application-owned shared HTTP client."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
        client: httpx.AsyncClient,
    ) -> None:
        if config.backend != "brave" or config.brave_api_key is None:
            raise ValueError(
                "BraveSearchProvider requires configured Brave credentials"
            )
        self._client = client
        self._api_key = config.brave_api_key
        self._timeout = httpx.Timeout(config.timeout_seconds)
        self._safe_search = config.safe_search
        self._citations = citation_registry

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult:
        params: dict[str, str | int] = {
            "q": query,
            "count": max_results + 1,
            "safesearch": self._safe_search,
        }
        if freshness != "any":
            params["freshness"] = {
                "day": "pd",
                "week": "pw",
                "month": "pm",
                "year": "py",
            }[freshness]
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self._api_key.get_secret_value(),
        }
        try:
            response = await self._client.get(
                _BRAVE_ENDPOINT,
                params=params,
                headers=headers,
                timeout=self._timeout,
                follow_redirects=False,
            )
        except httpx.TimeoutException as error:
            raise WebSearchError("timeout", cause_type=type(error).__name__) from None
        except httpx.HTTPError as error:
            raise WebSearchError(
                "unavailable", cause_type=type(error).__name__
            ) from None

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
            web = payload.get("web")
            if web is None:
                rows: list[Any] = []
            elif isinstance(web, Mapping) and isinstance(web.get("results"), list):
                rows = web["results"]
            else:
                raise TypeError
            return normalize_search_rows(
                query=query,
                rows=rows,
                max_results=max_results,
                citations=self._citations,
                url_fields=("url",),
                snippet_fields=("description", "snippet"),
                source_fields=("source", "profile"),
                published_fields=("page_age", "age"),
            )
        except WebSearchError:
            raise
        except (TypeError, ValueError) as error:
            raise WebSearchError(
                "invalid_response", cause_type=type(error).__name__
            ) from None


__all__ = ["BraveSearchProvider"]
