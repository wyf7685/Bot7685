from collections.abc import Mapping

import httpx2

from ....config import WebSearchConfig
from ....contracts.web import (
    CitationRegistry,
    SearchFreshness,
    WebSearchProvider,
    WebSearchResult,
)
from .common import (
    SearchDiagnosticParameter,
    SearchDiagnosticReason,
    WebSearchError,
    normalize_search_rows,
)

_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_TAVILY_REQUEST_PARAMETERS: tuple[SearchDiagnosticParameter, ...] = (
    "include_answer",
    "include_images",
    "include_raw_content",
    "max_results",
    "query",
    "safe_search",
    "search_depth",
    "time_range",
    "topic",
)


def _tavily_validation_parameter(
    message: str,
) -> SearchDiagnosticParameter | None:
    normalized = message.casefold().replace("_", " ")
    normalized = normalized.replace("'", "").replace('"', "")
    normalized = " ".join(normalized.split())
    for parameter in _TAVILY_REQUEST_PARAMETERS:
        name = parameter.replace("_", " ")
        if any(
            phrase in normalized
            for phrase in (
                f"invalid {name}",
                f"invalid parameter {name}",
                f"{name} is invalid",
                f"{name} is not supported",
                f"unsupported {name}",
            )
        ):
            return parameter
    return None


def _tavily_error_details(
    response: httpx2.Response,
) -> tuple[SearchDiagnosticReason, SearchDiagnosticParameter | None]:
    defaults: dict[int, SearchDiagnosticReason] = {
        400: "invalid_request",
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
        return default, None
    if not isinstance(payload, Mapping):
        return default, None
    detail = payload.get("detail")
    message = detail.get("error") if isinstance(detail, Mapping) else detail
    if not isinstance(message, str):
        return default, None
    normalized = " ".join(message.casefold().split())
    if response.status_code == 400:
        return "invalid_request", _tavily_validation_parameter(message)
    if any(term in normalized for term in ("expired", "deactivated", "inactive")):
        return "inactive_api_key", None
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
        return "invalid_api_key", None
    if "only available on" in normalized or "not available on" in normalized:
        return "feature_not_available", None
    if "usage limit" in normalized or "pay-as-you-go limit" in normalized:
        return "usage_limit", None
    if "excessive requests" in normalized or "request has been blocked" in normalized:
        return "request_blocked", None
    return default, None


class TavilySearchProvider(WebSearchProvider):
    """Tavily web search using an application-owned shared HTTP client."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
        client: httpx2.AsyncClient,
    ) -> None:
        if config.backend != "tavily" or config.tavily_api_key is None:
            raise ValueError(
                "TavilySearchProvider requires configured Tavily credentials"
            )
        self._client = client
        self._api_key = config.tavily_api_key
        self._timeout = httpx2.Timeout(config.timeout_seconds)
        # Tavily supports safe_search on all plans, but not with fast or
        # ultra-fast depths. This provider uses basic, so strict enables it.
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
        except httpx2.TimeoutException as error:
            error.add_note("stage=web_search operation=provider_request")
            raise WebSearchError("timeout", cause_type=type(error).__name__) from error
        except httpx2.HTTPError as error:
            error.add_note("stage=web_search operation=provider_request")
            raise WebSearchError(
                "unavailable", cause_type=type(error).__name__
            ) from error

        if response.status_code in (429, 432, 433):
            reason, _ = _tavily_error_details(response)
            raise WebSearchError(
                "rate_limited",
                status_code=response.status_code,
                reason=reason,
            )
        if response.status_code in (401, 403):
            reason, _ = _tavily_error_details(response)
            raise WebSearchError(
                "configuration",
                status_code=response.status_code,
                reason=reason,
            )
        if response.status_code == 400:
            reason, request_field = _tavily_error_details(response)
            raise WebSearchError(
                "unavailable",
                status_code=response.status_code,
                reason=reason,
                request_field=request_field,
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
            error.add_note("stage=web_search operation=response_parse")
            raise WebSearchError(
                "invalid_response", cause_type=type(error).__name__
            ) from error


__all__ = ["TavilySearchProvider"]
