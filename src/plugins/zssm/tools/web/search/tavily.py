from collections.abc import Mapping

import httpx

from ....config import WebSearchConfig
from ....contracts.web import (
    CitationRegistry,
    SearchFreshness,
    WebSearchProvider,
    WebSearchResult,
)
from .common import SearchDiagnosticReason, WebSearchError, normalize_search_rows

_TAVILY_ENDPOINT = "https://api.tavily.com/search"


def _tavily_error_reason(response: httpx.Response) -> SearchDiagnosticReason:
    defaults: dict[int, SearchDiagnosticReason] = {
        401: "invalid_api_key",
        403: "forbidden",
        429: "request_blocked",
        432: "usage_limit",
        433: "usage_limit",
    }
    default = defaults.get(response.status_code, "forbidden")
    try:
        payload = response.json()
    except TypeError, ValueError:
        return default
    if not isinstance(payload, Mapping):
        return default
    detail = payload.get("detail")
    message = detail.get("error") if isinstance(detail, Mapping) else detail
    if not isinstance(message, str):
        return default
    normalized = " ".join(message.casefold().split())
    if any(term in normalized for term in ("expired", "deactivated", "inactive")):
        return "inactive_api_key"
    if any(
        term in normalized
        for term in (
            "invalid api key",
            "api key is invalid",
            "missing api key",
            "api key is missing",
            "unauthorized",
            "not authorized",
        )
    ):
        return "invalid_api_key"
    if "only available on" in normalized or "not available on" in normalized:
        return "feature_not_available"
    if "usage limit" in normalized or "pay-as-you-go limit" in normalized:
        return "usage_limit"
    if "excessive requests" in normalized or "request has been blocked" in normalized:
        return "request_blocked"
    return default


class TavilySearchProvider(WebSearchProvider):
    """Tavily web search using an application-owned shared HTTP client."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
        client: httpx.AsyncClient,
    ) -> None:
        if config.backend != "tavily" or config.tavily_api_key is None:
            raise ValueError(
                "TavilySearchProvider requires configured Tavily credentials"
            )
        self._client = client
        self._api_key = config.tavily_api_key
        self._timeout = httpx.Timeout(config.timeout_seconds)
        # Tavily's enhanced safe search is boolean and enterprise-only. The
        # shared "moderate" setting must not opt into that strict feature.
        self._safe_search = config.safe_search == "strict"
        self._citations = citation_registry

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult:
        body: dict[str, str | int | bool] = {
            "query": query,
            "search_depth": "basic",
            "topic": "general",
            "max_results": max_results + 1,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "safe_search": self._safe_search,
        }
        if freshness != "any":
            body["time_range"] = freshness
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        try:
            response = await self._client.post(
                _TAVILY_ENDPOINT,
                json=body,
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

        if response.status_code in (429, 432, 433):
            raise WebSearchError(
                "rate_limited",
                status_code=response.status_code,
                reason=_tavily_error_reason(response),
            )
        if response.status_code in (401, 403):
            raise WebSearchError(
                "configuration",
                status_code=response.status_code,
                reason=_tavily_error_reason(response),
            )
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
                snippet_fields=("content", "snippet", "description"),
                source_fields=("domain", "source"),
                published_fields=("published_date", "published"),
            )
        except WebSearchError:
            raise
        except (TypeError, ValueError) as error:
            raise WebSearchError(
                "invalid_response", cause_type=type(error).__name__
            ) from None


__all__ = ["TavilySearchProvider"]
