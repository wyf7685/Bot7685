from __future__ import annotations

import codecs
import hashlib
import ipaddress
import math
import re
import socket
import zlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import Any, Literal, Self, cast
from urllib.parse import SplitResult, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import anyio
import httpx
from anyio.to_thread import run_sync

from src.service.llm import BoundTool, JSONValue, ToolOutput

from ..config import FetchPageConfig, WebSearchConfig
from ..contracts import (
    Citation,
    CitationRegistry,
    CitationSourceKind,
    FetchPageArgs,
    SearchFreshness,
    SearchResult,
    WebPageResult,
    WebSearchArgs,
    WebSearchProvider,
    WebSearchResult,
    ZssmToolContext,
    bind_web_search_args,
)
from .web_sources.contracts import DownloadedPage as _DownloadedPage
from .web_sources.contracts import ExtractedPage as _ExtractedPage
from .web_sources.contracts import SourceAdapterError
from .web_sources.contracts import ValidatedTarget as _ValidatedTarget
from .web_sources.registry import DEFAULT_SOURCE_REGISTRY, SourceRegistry

_BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_TAVILY_ENDPOINT = "https://api.tavily.com/search"
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_DEFAULT_PORTS = {"http": 80, "https": 443}
_USER_AGENT = "Bot7685-ZSSM/1.0"
_ROBOTS_CACHE_SECONDS = 300.0
_MAX_URL_CHARS = 4096
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CAUSE_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,79}$")

type SearchErrorCode = Literal[
    "configuration",
    "invalid_response",
    "rate_limited",
    "timeout",
    "unavailable",
]
type SearchDiagnosticReason = Literal[
    "forbidden",
    "feature_not_available",
    "inactive_api_key",
    "invalid_api_key",
    "no_results",
    "request_blocked",
    "usage_limit",
]
type FetchErrorCode = Literal[
    "content_encoding",
    "decode",
    "dns",
    "extract",
    "http_status",
    "network",
    "peer_mismatch",
    "redirect",
    "robots_denied",
    "robots_unavailable",
    "timeout",
    "too_large",
    "unsafe_url",
    "unsupported_content",
]
type AddressResolver = Callable[[str, int], Awaitable[Sequence[str]]]
type _IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type _RobotsMode = Literal["enforce", "skip"]


class WebSearchError(RuntimeError):
    """A provider failure with only stable, non-sensitive diagnostic facts."""

    def __init__(
        self,
        code: SearchErrorCode,
        *,
        cause_type: str | None = None,
        status_code: int | None = None,
        reason: SearchDiagnosticReason | None = None,
    ) -> None:
        if cause_type is not None and not _CAUSE_TYPE_RE.fullmatch(cause_type):
            raise ValueError("web search cause type is invalid")
        if status_code is not None and not 100 <= status_code <= 599:
            raise ValueError("web search status code is invalid")
        self.code = code
        self.cause_type = cause_type
        self.status_code = status_code
        self.reason = reason
        super().__init__(code)


class SafePageFetchError(RuntimeError):
    """A safe-fetch failure that never embeds a URL, body, or transport message."""

    def __init__(self, code: FetchErrorCode, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class InvocationCitationRegistry(CitationRegistry):
    """Invocation-local stable citation allocation with normalized URL aliases."""

    def __init__(self) -> None:
        self._by_url: dict[str, str] = {}
        self._citations: dict[str, Citation] = {}
        self._allocation_order: list[str] = []
        self._used: set[str] = set()

    def register(
        self,
        *,
        source_kind: CitationSourceKind,
        title: str,
        url: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation:
        normalized_url = _normalize_http_url(url)
        if citation_id := self._by_url.get(normalized_url):
            existing = self._citations[citation_id]
            updated = _merge_citation(
                existing,
                source_kind=source_kind,
                title=title,
                url=normalized_url,
                source=source,
                published=published,
            )
            self._citations[citation_id] = updated
            return updated

        citation_id = f"s{len(self._allocation_order) + 1}"
        citation = Citation(
            citation_id=citation_id,
            source_kind=source_kind,
            title=title,
            url=normalized_url,
            source=source,
            published=published,
        )
        self._by_url[normalized_url] = citation_id
        self._citations[citation_id] = citation
        self._allocation_order.append(citation_id)
        return citation

    def register_page(
        self,
        *,
        requested_url: str,
        final_url: str,
        title: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation:
        """Register a fetched page while reusing a prior search citation."""

        requested = _normalize_http_url(requested_url)
        final = _normalize_http_url(final_url)
        requested_id = self._by_url.get(requested)
        final_id = self._by_url.get(final)

        if requested_id is None and final_id is None:
            citation = self.register(
                source_kind=CitationSourceKind.PAGE,
                title=title,
                url=final,
                source=source,
                published=published,
            )
            self._by_url[requested] = citation.citation_id
            return citation

        citation_id = requested_id or cast("str", final_id)
        existing = self._citations[citation_id]
        citation_url = final if final_id in (None, citation_id) else requested
        updated = Citation(
            citation_id=citation_id,
            source_kind=CitationSourceKind.PAGE,
            title=title,
            url=citation_url,
            source=source or existing.source,
            published=published or existing.published,
        )
        self._citations[citation_id] = updated
        self._by_url[requested] = citation_id
        if final_id in (None, citation_id):
            self._by_url[final] = citation_id
        return updated

    def get(self, citation_id: str) -> Citation | None:
        return self._citations.get(citation_id)

    def mark_used(self, citation_id: str) -> bool:
        if citation_id not in self._citations:
            return False
        self._used.add(citation_id)
        return True

    def used_citations(self) -> tuple[Citation, ...]:
        return tuple(
            self._citations[citation_id]
            for citation_id in self._allocation_order
            if citation_id in self._used
        )


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
            return _normalize_search_rows(
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
            return _normalize_search_rows(
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


class _DDGSBackendUnavailable(RuntimeError):
    pass


class DDGSSearchProvider(WebSearchProvider):
    """A lazy, bounded DDGS provider pinned to one configured backend."""

    def __init__(
        self,
        config: WebSearchConfig,
        citation_registry: CitationRegistry,
        *,
        limiter: anyio.CapacityLimiter | None = None,
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
        self._limiter = limiter or anyio.CapacityLimiter(config.ddgs_max_parallel)

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
            return _normalize_search_rows(
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
        from ddgs import DDGS
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


@dataclass(slots=True)
class _RobotsCacheEntry:
    expires_at: float
    mode: Literal["allow", "deny", "unavailable", "rules"]
    parser: RobotFileParser | None = None


class HttpxSafePageFetcher:
    """SSRF-safe HTTP fetcher that connects only to prevalidated DNS answers."""

    def __init__(
        self,
        config: FetchPageConfig,
        citation_registry: InvocationCitationRegistry,
        *,
        resolver: AddressResolver | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = monotonic,
        source_registry: SourceRegistry | None = None,
    ) -> None:
        self._config = config
        self._citations = citation_registry
        self._resolver = resolver or _resolve_system_addresses
        self._clock = clock
        self._source_registry = source_registry or DEFAULT_SOURCE_REGISTRY
        self._robots_cache: dict[str, _RobotsCacheEntry] = {}
        if transport is None:
            transport = httpx.AsyncHTTPTransport(
                trust_env=False,
                http1=True,
                http2=False,
                limits=httpx.Limits(max_keepalive_connections=0),
            )
        self._client = httpx.AsyncClient(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(None),
        )

    @property
    def respect_robots(self) -> bool:
        return self._config.respect_robots

    @property
    def max_redirects(self) -> int:
        return self._config.max_redirects

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def download(
        self,
        url: str,
        *,
        accept: str,
        allowed_content_types: Sequence[str],
    ) -> _DownloadedPage:
        return await self._download(
            url,
            allow_http_errors=False,
            robots_mode="enforce" if self._config.respect_robots else "skip",
            accept=accept,
            allowed_content_types=allowed_content_types,
        )

    async def resolve_redirects(
        self,
        url: str,
        *,
        allowed_hosts: frozenset[str],
    ) -> str | None:
        current = _validate_target(url)
        redirects = 0
        try:
            with anyio.fail_after(self._config.total_timeout_seconds):
                while True:
                    if current.hostname not in allowed_hosts:
                        return None
                    if self._config.respect_robots:
                        await self._enforce_robots(current)
                    addresses = await self._resolve(current.hostname, current.port)
                    request = _build_pinned_request(
                        current,
                        addresses[0],
                        method="HEAD",
                    )
                    response: httpx.Response | None = None
                    try:
                        try:
                            response = await self._client.send(
                                request,
                                stream=True,
                                follow_redirects=False,
                                auth=None,
                            )
                        except httpx.TimeoutException:
                            raise SafePageFetchError("timeout") from None
                        except httpx.HTTPError:
                            raise SafePageFetchError("network") from None
                        _verify_peer(response, addresses)
                        if response.status_code not in _REDIRECT_STATUSES:
                            return current.url
                        if redirects >= self._config.max_redirects:
                            raise SafePageFetchError("redirect")
                        location = response.headers.get("location")
                        if location is None:
                            raise SafePageFetchError("redirect")
                        try:
                            current = _validate_target(urljoin(current.url, location))
                        except TypeError, ValueError, SafePageFetchError:
                            raise SafePageFetchError("redirect") from None
                        redirects += 1
                    finally:
                        if response is not None:
                            await _close_response(response)
        except TimeoutError:
            raise SafePageFetchError("timeout") from None

    async def fetch(self, url: str) -> WebPageResult:
        initial = _validate_target(url)
        match = self._source_registry.match(initial)
        try:
            with anyio.fail_after(self._config.total_timeout_seconds):
                if match is not None:
                    adapter, source_target = match
                    specialized = await adapter.fetch_specialized(source_target, self)
                    if specialized is not None:
                        return self._make_page_result(
                            requested_url=initial.url,
                            final_url=specialized.final_url,
                            extracted=specialized.extracted,
                        )

                downloaded = await self._download(
                    initial.url,
                    allow_http_errors=False,
                    robots_mode="enforce" if self._config.respect_robots else "skip",
                )
                final_target = _validate_target(downloaded.final_url)
                final_match = self._source_registry.match(final_target)
                if final_match is not None:
                    final_adapter, final_source_target = final_match
                    extracted = final_adapter.extract_html(
                        html=_decode_text(downloaded.body, downloaded.charset),
                        final_url=downloaded.final_url,
                    )
                    if extracted is not None:
                        return self._make_page_result(
                            requested_url=initial.url,
                            final_url=final_source_target.canonical_url,
                            extracted=extracted,
                        )
                extracted = await self._extract(downloaded)
                return self._make_page_result(
                    requested_url=initial.url,
                    final_url=downloaded.final_url,
                    extracted=extracted,
                )
        except SourceAdapterError:
            raise SafePageFetchError("extract") from None
        except TimeoutError:
            raise SafePageFetchError("timeout") from None

    def _make_page_result(
        self,
        *,
        requested_url: str,
        final_url: str,
        extracted: _ExtractedPage,
    ) -> WebPageResult:
        full_text = extracted.text
        truncated = len(full_text) > self._config.max_text_chars
        text = (
            full_text[: self._config.max_text_chars].rstrip()
            if truncated
            else full_text
        )
        if not text:
            raise SafePageFetchError("extract")
        content_sha256 = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
        citation = self._citations.register_page(
            requested_url=requested_url,
            final_url=final_url,
            title=extracted.title,
            source=extracted.site or urlsplit(final_url).hostname,
            published=extracted.published,
        )
        return WebPageResult(
            title=extracted.title,
            author=extracted.author,
            site=extracted.site,
            published=extracted.published,
            language=extracted.language,
            text=text,
            truncated=truncated,
            final_url=final_url,
            content_sha256=content_sha256,
            citation_id=citation.citation_id,
        )

    async def _download(
        self,
        url: str,
        *,
        allow_http_errors: bool,
        robots_mode: _RobotsMode,
        accept: str = "text/html,application/xhtml+xml,text/plain,text/markdown",
        accept_encoding: str = "gzip, deflate",
        allowed_content_types: Sequence[str] | None = None,
    ) -> _DownloadedPage:
        current = _validate_target(url)
        redirects = 0
        while True:
            if robots_mode == "enforce":
                await self._enforce_robots(current)
            addresses = await self._resolve(current.hostname, current.port)
            chosen = addresses[0]
            request = _build_pinned_request(
                current,
                chosen,
                accept=accept,
                accept_encoding=accept_encoding,
            )
            response: httpx.Response | None = None
            try:
                try:
                    response = await self._client.send(
                        request,
                        stream=True,
                        follow_redirects=False,
                        auth=None,
                    )
                except httpx.TimeoutException:
                    raise SafePageFetchError("timeout") from None
                except httpx.HTTPError:
                    raise SafePageFetchError("network") from None

                _verify_peer(response, addresses)
                if response.status_code in _REDIRECT_STATUSES:
                    if redirects >= self._config.max_redirects:
                        raise SafePageFetchError("redirect")
                    location = response.headers.get("location")
                    if location is None:
                        raise SafePageFetchError("redirect")
                    try:
                        redirected = urljoin(current.url, location)
                        current = _validate_target(redirected)
                    except TypeError, ValueError, SafePageFetchError:
                        raise SafePageFetchError("redirect") from None
                    redirects += 1
                    continue

                if not 200 <= response.status_code < 300:
                    if allow_http_errors and 400 <= response.status_code < 600:
                        return _DownloadedPage(
                            status_code=response.status_code,
                            final_url=current.url,
                            media_type=None,
                            charset=None,
                            body=b"",
                        )
                    raise SafePageFetchError(
                        "http_status",
                        status_code=response.status_code,
                    )

                media_type, charset = self._validate_content_type(
                    response.headers,
                    allowed_content_types=allowed_content_types,
                )
                wire = await self._read_wire_body(response)
                encoding = self._content_encoding(response.headers)
                body = _decode_content(
                    wire,
                    encoding=encoding,
                    max_decoded_bytes=self._config.max_decoded_bytes,
                    max_expansion_ratio=self._config.max_expansion_ratio,
                )
                return _DownloadedPage(
                    status_code=response.status_code,
                    final_url=current.url,
                    media_type=media_type,
                    charset=charset,
                    body=body,
                )
            finally:
                if response is not None:
                    await _close_response(response)

    async def _resolve(self, hostname: str, port: int) -> tuple[_IPAddress, ...]:
        try:
            raw_addresses = await self._resolver(hostname, port)
        except Exception:
            raise SafePageFetchError("dns") from None
        addresses: set[_IPAddress] = set()
        for raw_address in raw_addresses:
            if not isinstance(raw_address, str) or "%" in raw_address:
                raise SafePageFetchError("unsafe_url")
            try:
                address = ipaddress.ip_address(raw_address)
            except ValueError:
                raise SafePageFetchError("dns") from None
            if not _is_unambiguous_global(address):
                raise SafePageFetchError("unsafe_url")
            addresses.add(address)
        if not addresses:
            raise SafePageFetchError("dns")
        return tuple(sorted(addresses, key=lambda item: (item.version, item.packed)))

    async def _read_wire_body(self, response: httpx.Response) -> bytes:
        lengths = response.headers.get_list("content-length")
        if len(lengths) > 1:
            raise SafePageFetchError("too_large")
        if lengths:
            try:
                content_length = int(lengths[0])
            except ValueError:
                raise SafePageFetchError("too_large") from None
            if content_length < 0 or content_length > self._config.max_wire_bytes:
                raise SafePageFetchError("too_large")

        wire = bytearray()
        if response.is_stream_consumed:
            if len(response.content) > self._config.max_wire_bytes:
                raise SafePageFetchError("too_large")
            return response.content
        try:
            async for chunk in response.aiter_raw():
                if len(wire) + len(chunk) > self._config.max_wire_bytes:
                    raise SafePageFetchError("too_large")
                wire.extend(chunk)
        except httpx.TimeoutException:
            raise SafePageFetchError("timeout") from None
        except httpx.HTTPError:
            raise SafePageFetchError("network") from None
        return bytes(wire)

    def _validate_content_type(
        self,
        headers: httpx.Headers,
        *,
        allowed_content_types: Sequence[str] | None = None,
    ) -> tuple[str, str | None]:
        values = headers.get_list("content-type")
        if len(values) != 1:
            raise SafePageFetchError("unsupported_content")
        parts = [part.strip() for part in values[0].split(";")]
        media_type = parts[0].casefold()
        allowed = (
            frozenset(allowed_content_types)
            if allowed_content_types is not None
            else self._config.allowed_content_types
        )
        if media_type not in allowed:
            raise SafePageFetchError("unsupported_content")
        charset: str | None = None
        for parameter in parts[1:]:
            name, separator, value = parameter.partition("=")
            if separator and name.strip().casefold() == "charset":
                candidate = value.strip().strip('"').strip("'")
                if not candidate or charset is not None:
                    raise SafePageFetchError("decode")
                charset = candidate
        return media_type, charset

    @staticmethod
    def _content_encoding(headers: httpx.Headers) -> str:
        values = headers.get_list("content-encoding")
        if not values:
            return "identity"
        if len(values) != 1 or "," in values[0]:
            raise SafePageFetchError("content_encoding")
        encoding = values[0].strip().casefold()
        if encoding not in {"identity", "gzip", "deflate"}:
            raise SafePageFetchError("content_encoding")
        return encoding

    async def _extract(self, downloaded: _DownloadedPage) -> _ExtractedPage:
        text = _decode_text(downloaded.body, downloaded.charset)
        hostname = cast("str", urlsplit(downloaded.final_url).hostname)
        if downloaded.media_type in {"text/plain", "text/markdown"}:
            normalized = _normalize_page_text(text)
            if not normalized:
                raise SafePageFetchError("extract")
            title = _plain_text_title(normalized, hostname, downloaded.media_type)
            return _ExtractedPage(title, None, hostname, None, None, normalized)

        try:
            extracted = await run_sync(
                partial(_extract_html_sync, text, downloaded.final_url, hostname),
                abandon_on_cancel=True,
            )
        except Exception:
            raise SafePageFetchError("extract") from None
        if not extracted.text:
            raise SafePageFetchError("extract")
        return extracted

    async def _enforce_robots(self, target: _ValidatedTarget) -> None:
        now = self._clock()
        cached = self._robots_cache.get(target.origin)
        if cached is None or cached.expires_at <= now:
            cached = await self._load_robots(target, now)
            self._robots_cache[target.origin] = cached

        if cached.mode == "unavailable":
            raise SafePageFetchError("robots_unavailable")
        if cached.mode == "deny":
            raise SafePageFetchError("robots_denied")
        if cached.mode == "rules" and (
            cached.parser is None
            or not cached.parser.can_fetch(_USER_AGENT, target.url)
        ):
            raise SafePageFetchError("robots_denied")

    async def _load_robots(
        self,
        target: _ValidatedTarget,
        now: float,
    ) -> _RobotsCacheEntry:
        expires_at = now + _ROBOTS_CACHE_SECONDS
        robots_url = f"{target.origin}/robots.txt"
        try:
            downloaded = await self._download(
                robots_url,
                allow_http_errors=True,
                robots_mode="skip",
                accept_encoding="identity",
            )
        except SafePageFetchError:
            return _RobotsCacheEntry(expires_at, "unavailable")

        if downloaded.status_code >= 500:
            return _RobotsCacheEntry(expires_at, "unavailable")
        if downloaded.status_code in (401, 403):
            return _RobotsCacheEntry(expires_at, "deny")
        if downloaded.status_code >= 400:
            return _RobotsCacheEntry(expires_at, "allow")
        try:
            robots_text = _decode_text(downloaded.body, downloaded.charset)
            parser = RobotFileParser()
            parser.set_url(robots_url)
            parser.parse(robots_text.splitlines())
        except Exception:
            return _RobotsCacheEntry(expires_at, "unavailable")
        return _RobotsCacheEntry(expires_at, "rules", parser)


async def resolve_card_urls(
    urls: Sequence[str],
    config: FetchPageConfig,
    *,
    source_registry: SourceRegistry | None = None,
) -> Mapping[str, str]:
    """Resolve supported card URLs through registered source adapters."""

    registry = source_registry or DEFAULT_SOURCE_REGISTRY
    async with HttpxSafePageFetcher(
        config,
        InvocationCitationRegistry(),
        source_registry=registry,
    ) as fetcher:
        return await registry.resolve_card_urls(urls, fetcher)


async def _close_response(response: httpx.Response) -> None:
    """Bound cleanup while shielding it from an expired or caller cancel scope."""

    with anyio.move_on_after(1.0, shield=True):
        with suppress(Exception):
            await response.aclose()


def create_web_search_provider(
    config: WebSearchConfig,
    citation_registry: InvocationCitationRegistry,
    *,
    client: httpx.AsyncClient | None = None,
    ddgs_limiter: anyio.CapacityLimiter | None = None,
) -> BraveSearchProvider | DDGSSearchProvider | TavilySearchProvider:
    """Create exactly the configured provider; never fall back to another backend."""

    if config.backend == "brave":
        if client is None:
            raise ValueError("a shared HTTP client is required for Brave search")
        return BraveSearchProvider(config, citation_registry, client)
    if config.backend == "tavily":
        if client is None:
            raise ValueError("a shared HTTP client is required for Tavily search")
        return TavilySearchProvider(config, citation_registry, client)
    if config.backend == "ddgs":
        return DDGSSearchProvider(config, citation_registry, limiter=ddgs_limiter)
    raise ValueError("unsupported web search backend")


def build_web_tools(
    context: ZssmToolContext,
) -> tuple[
    BoundTool[ZssmToolContext, WebSearchArgs],
    BoundTool[ZssmToolContext, FetchPageArgs],
]:
    """Bind strict model schemas to one private invocation context."""

    search_arguments = bind_web_search_args(context.web_search_config)
    return (
        BoundTool(
            name="web_search",
            description=(
                "Search the configured web provider. Results include stable "
                "citation IDs that should be referenced when used in the answer."
            ),
            arguments_type=search_arguments,
            context=context,
            handler=_handle_web_search,
        ),
        BoundTool(
            name="fetch_page",
            description=(
                "Safely fetch and extract an HTTP or HTTPS page. The result includes a "
                "stable citation ID that should be referenced when used in the answer."
            ),
            arguments_type=FetchPageArgs,
            context=context,
            handler=_handle_fetch_page,
        ),
    )


async def _handle_web_search(
    context: ZssmToolContext,
    arguments: WebSearchArgs,
) -> ToolOutput:
    try:
        result = await context.search_provider.search(
            query=arguments.query,
            max_results=arguments.max_results,
            freshness=arguments.freshness,
        )
    except WebSearchError as error:
        backend = context.web_search_config.backend
        diagnostic_parts = [f"backend={backend}"]
        if backend == "ddgs":
            diagnostic_parts.append(f"engine={context.web_search_config.ddgs_backend}")
        if error.status_code is not None:
            diagnostic_parts.append(f"status={error.status_code}")
        if error.cause_type is not None:
            diagnostic_parts.append(f"cause={error.cause_type}")
        if error.reason is not None:
            diagnostic_parts.append(f"reason={error.reason}")
        return ToolOutput(
            value={"status": "error", "error": {"code": error.code}},
            summary="web_search status=error results=0 truncated=false",
            reported_error_code=f"web_search_{error.code}",
            diagnostic=" ".join(diagnostic_parts),
        )

    citations: list[JSONValue] = []
    for item in result.results:
        citation = context.citation_registry.get(item.citation_id)
        if citation is None:
            raise RuntimeError("search provider returned an unknown citation")
        citations.append(_citation_json(citation))
    results: list[JSONValue] = [_search_result_json(item) for item in result.results]
    value: dict[str, JSONValue] = {
        "status": "ok",
        "query": result.query,
        "results": results,
        "truncated": result.truncated,
        "citations": citations,
    }
    output = ToolOutput(
        value=value,
        summary=(
            f"web_search status=ok results={result.returned} "
            f"truncated={str(result.truncated).lower()}"
        ),
    )
    for item in result.results:
        context.citation_registry.mark_used(item.citation_id)
    return output


async def _handle_fetch_page(
    context: ZssmToolContext,
    arguments: FetchPageArgs,
) -> ToolOutput:
    input_host = _safe_trace_hostname(arguments.url)
    try:
        page = await context.page_fetcher.fetch(arguments.url)
    except SafePageFetchError as error:
        status = str(error.status_code) if error.status_code is not None else error.code
        return ToolOutput(
            value={"status": "error", "error": {"code": error.code}},
            summary=f"fetch_page status={status} host={input_host} chars=0",
            reported_error_code=f"fetch_page_{error.code}",
        )

    citation = context.citation_registry.get(page.citation_id)
    if citation is None:
        raise RuntimeError("page fetcher returned an unknown citation")
    host = _safe_trace_hostname(page.final_url)
    output = ToolOutput(
        value={
            "status": "ok",
            "page": _web_page_json(page),
            "citations": [_citation_json(citation)],
        },
        summary=f"fetch_page status=ok host={host} chars={len(page.text)}",
    )
    context.citation_registry.mark_used(page.citation_id)
    return output


def _normalize_search_rows(
    *,
    query: str,
    rows: Sequence[Any],
    max_results: int,
    citations: CitationRegistry,
    url_fields: Sequence[str],
    snippet_fields: Sequence[str],
    source_fields: Sequence[str],
    published_fields: Sequence[str],
) -> WebSearchResult:
    normalized: list[SearchResult] = []
    seen_urls: set[str] = set()
    truncated = len(rows) > max_results
    for raw in rows:
        if len(normalized) >= max_results:
            truncated = True
            break
        if not isinstance(raw, Mapping):
            continue
        try:
            title = _required_field(raw, ("title", "name"), maximum=500)
            url = _normalize_http_url(
                _required_field(raw, url_fields, maximum=_MAX_URL_CHARS)
            )
            if url in seen_urls:
                continue
            snippet = _optional_field(raw, snippet_fields, maximum=2000) or ""
            source = _optional_field(
                raw, source_fields, maximum=300
            ) or _source_from_url(url)
            published = _optional_field(raw, published_fields, maximum=200)
            language = _optional_field(raw, ("language", "lang"), maximum=50)
            citation = citations.register(
                source_kind=CitationSourceKind.SEARCH,
                title=title,
                url=url,
                source=source,
                published=published,
            )
        except TypeError, ValueError, SafePageFetchError:
            continue
        seen_urls.add(url)
        normalized.append(
            SearchResult(
                rank=len(normalized) + 1,
                title=title,
                url=url,
                snippet=snippet,
                source=source,
                published=published,
                language=language,
                citation_id=citation.citation_id,
            )
        )
    return WebSearchResult(query=query, results=tuple(normalized), truncated=truncated)


def _required_field(
    row: Mapping[str, Any],
    names: Sequence[str],
    *,
    maximum: int,
) -> str:
    value = _optional_field(row, names, maximum=maximum)
    if value is None:
        raise ValueError
    return value


def _optional_field(
    row: Mapping[str, Any],
    names: Sequence[str],
    *,
    maximum: int,
) -> str | None:
    for name in names:
        value = row.get(name)
        if isinstance(value, str):
            normalized = _normalize_single_line(value, maximum)
            if normalized:
                return normalized
        elif isinstance(value, Mapping):
            for nested_name in ("long_name", "name"):
                nested = value.get(nested_name)
                if isinstance(nested, str):
                    normalized = _normalize_single_line(nested, maximum)
                    if normalized:
                        return normalized
    return None


def _merge_citation(
    existing: Citation,
    *,
    source_kind: CitationSourceKind,
    title: str,
    url: str,
    source: str | None,
    published: str | None,
) -> Citation:
    if (
        source_kind is CitationSourceKind.PAGE
        or existing.source_kind is CitationSourceKind.PAGE
    ):
        use_new = source_kind is CitationSourceKind.PAGE
        return Citation(
            citation_id=existing.citation_id,
            source_kind=CitationSourceKind.PAGE,
            title=title if use_new else existing.title,
            url=url,
            source=(source if use_new else existing.source)
            or existing.source
            or source,
            published=(published if use_new else existing.published)
            or existing.published
            or published,
        )
    return Citation(
        citation_id=existing.citation_id,
        source_kind=existing.source_kind,
        title=existing.title,
        url=existing.url,
        source=existing.source or source,
        published=existing.published or published,
    )


def _normalize_http_url(url: str) -> str:
    return _validate_target(url).url


def _validate_target(url: str) -> _ValidatedTarget:
    if not isinstance(url, str):
        raise SafePageFetchError("unsafe_url")
    url = url.strip()
    if (
        not url
        or len(url) > _MAX_URL_CHARS
        or any(ord(character) < 32 for character in url)
    ):
        raise SafePageFetchError("unsafe_url")
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise SafePageFetchError("unsafe_url") from None
    scheme = parsed.scheme.casefold()
    if scheme not in _DEFAULT_PORTS or not parsed.netloc or "\\" in parsed.netloc:
        raise SafePageFetchError("unsafe_url")
    if parsed.username is not None or parsed.password is not None:
        raise SafePageFetchError("unsafe_url")
    hostname = parsed.hostname
    if hostname is None:
        raise SafePageFetchError("unsafe_url")
    hostname = hostname.rstrip(".")
    if not hostname:
        raise SafePageFetchError("unsafe_url")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise SafePageFetchError("unsafe_url")
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except UnicodeError, ValueError:
        raise SafePageFetchError("unsafe_url") from None
    if len(ascii_hostname) > 253 or any(
        not _HOST_LABEL_RE.fullmatch(label) for label in ascii_hostname.split(".")
    ):
        raise SafePageFetchError("unsafe_url")
    if port != _DEFAULT_PORTS[scheme]:
        raise SafePageFetchError("unsafe_url")

    path = parsed.path or "/"
    canonical = SplitResult(scheme, ascii_hostname, path, parsed.query, "")
    normalized_url = urlunsplit(canonical)
    origin = f"{scheme}://{ascii_hostname}"
    return _ValidatedTarget(
        url=normalized_url,
        scheme=cast("Literal['http', 'https']", scheme),
        hostname=ascii_hostname,
        port=port,
        origin=origin,
        host_header=ascii_hostname,
    )


async def _resolve_system_addresses(hostname: str, port: int) -> Sequence[str]:
    infos = await anyio.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(str(info[4][0]) for info in infos)


def _is_unambiguous_global(address: _IPAddress) -> bool:
    if not address.is_global:
        return False
    if isinstance(address, ipaddress.IPv6Address):
        if (
            address.ipv4_mapped is not None
            or address.sixtofour is not None
            or address.teredo is not None
        ):
            return False
        if address.scope_id is not None:
            return False
    return not (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_private
        or address.is_reserved
        or address.is_unspecified
    )


def _build_pinned_request(
    target: _ValidatedTarget,
    address: _IPAddress,
    *,
    method: Literal["GET", "HEAD"] = "GET",
    accept: str = "text/html,application/xhtml+xml,text/plain,text/markdown",
    accept_encoding: str = "gzip, deflate",
) -> httpx.Request:
    parsed = urlsplit(target.url)
    connect_host = f"[{address}]" if address.version == 6 else str(address)
    connect_url = urlunsplit(
        (target.scheme, connect_host, parsed.path, parsed.query, "")
    )
    extensions: dict[str, Any] = {}
    if target.scheme == "https":
        extensions["sni_hostname"] = target.hostname
    return httpx.Request(
        method,
        connect_url,
        headers={
            "Host": target.host_header,
            "User-Agent": _USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": accept_encoding,
        },
        extensions=extensions,
    )


def _verify_peer(response: httpx.Response, expected: Sequence[_IPAddress]) -> None:
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        return
    peer = stream.get_extra_info("server_addr")
    if peer is None:
        return
    raw_address = peer[0] if isinstance(peer, tuple) and peer else peer
    if not isinstance(raw_address, str):
        raise SafePageFetchError("peer_mismatch")
    try:
        actual = ipaddress.ip_address(raw_address.split("%", 1)[0])
    except ValueError:
        raise SafePageFetchError("peer_mismatch") from None
    if actual not in expected or not _is_unambiguous_global(actual):
        raise SafePageFetchError("peer_mismatch")


def _decode_content(
    wire: bytes,
    *,
    encoding: str,
    max_decoded_bytes: int,
    max_expansion_ratio: float,
) -> bytes:
    if encoding == "identity":
        decoded = wire
    elif encoding == "gzip":
        decoded = _bounded_zlib_decompress(wire, 16 + zlib.MAX_WBITS, max_decoded_bytes)
    elif encoding == "deflate":
        try:
            decoded = _bounded_zlib_decompress(wire, zlib.MAX_WBITS, max_decoded_bytes)
        except SafePageFetchError as error:
            if error.code == "too_large":
                raise
            decoded = _bounded_zlib_decompress(wire, -zlib.MAX_WBITS, max_decoded_bytes)
    else:
        raise SafePageFetchError("content_encoding")
    if len(decoded) > max_decoded_bytes:
        raise SafePageFetchError("too_large")
    if len(decoded) > max(1, len(wire)) * max_expansion_ratio:
        raise SafePageFetchError("too_large")
    return decoded


def _bounded_zlib_decompress(data: bytes, wbits: int, limit: int) -> bytes:
    decoder = zlib.decompressobj(wbits)
    output = bytearray()
    pending = data
    try:
        while pending:
            room = limit + 1 - len(output)
            if room <= 0:
                raise SafePageFetchError("too_large")
            output.extend(decoder.decompress(pending, room))
            if len(output) > limit:
                raise SafePageFetchError("too_large")
            next_pending = decoder.unconsumed_tail
            if not next_pending:
                break
            if next_pending == pending:
                raise SafePageFetchError("decode")
            pending = next_pending
        room = limit + 1 - len(output)
        output.extend(decoder.flush(room))
    except zlib.error:
        raise SafePageFetchError("decode") from None
    if len(output) > limit:
        raise SafePageFetchError("too_large")
    if not decoder.eof or decoder.unused_data:
        raise SafePageFetchError("decode")
    return bytes(output)


def _decode_text(body: bytes, charset: str | None) -> str:
    encoding = charset or "utf-8"
    try:
        codecs.lookup(encoding)
        return body.decode(encoding, errors="replace").lstrip("\ufeff")
    except LookupError, UnicodeError:
        raise SafePageFetchError("decode") from None


def _extract_html_sync(html: str, url: str, hostname: str) -> _ExtractedPage:
    from trafilatura import bare_extraction

    document = bare_extraction(
        html,
        url=url,
        include_comments=False,
        include_tables=True,
        with_metadata=True,
    )
    if document is None:
        raise ValueError
    text = _normalize_page_text(getattr(document, "text", None) or "")
    if not text:
        raise ValueError
    title = (
        _normalize_single_line(getattr(document, "title", None) or "", 500) or hostname
    )
    author = _optional_metadata(getattr(document, "author", None), 300)
    site = _optional_metadata(getattr(document, "sitename", None), 300) or hostname
    published = _optional_metadata(getattr(document, "date", None), 100)
    language = _optional_metadata(getattr(document, "language", None), 50)
    return _ExtractedPage(title, author, site, published, language, text)


def _optional_metadata(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return _normalize_single_line(value, maximum) or None


def _normalize_page_text(value: str) -> str:
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


def _plain_text_title(text: str, hostname: str, media_type: str | None) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if media_type == "text/markdown":
        first_line = first_line.lstrip("#").strip()
    return _normalize_single_line(first_line, 500) or hostname


def _normalize_single_line(value: str, maximum: int) -> str:
    value = _CONTROL_RE.sub("", value)
    value = " ".join(value.split())
    return value[:maximum].strip()


def _source_from_url(url: str) -> str:
    return cast("str", urlsplit(url).hostname)


def _citation_json(citation: Citation) -> dict[str, JSONValue]:
    return {
        "citation_id": citation.citation_id,
        "source_kind": citation.source_kind.value,
        "title": citation.title,
        "url": citation.url,
        "source": citation.source,
        "published": citation.published,
    }


def _search_result_json(result: SearchResult) -> dict[str, JSONValue]:
    return {
        "rank": result.rank,
        "title": result.title,
        "url": result.url,
        "snippet": result.snippet,
        "source": result.source,
        "published": result.published,
        "language": result.language,
        "citation_id": result.citation_id,
    }


def _web_page_json(page: WebPageResult) -> dict[str, JSONValue]:
    return {
        "title": page.title,
        "author": page.author,
        "site": page.site,
        "published": page.published,
        "language": page.language,
        "text": page.text,
        "truncated": page.truncated,
        "final_url": page.final_url,
        "content_sha256": page.content_sha256,
        "citation_id": page.citation_id,
    }


def _safe_trace_hostname(url: str) -> str:
    try:
        hostname = urlsplit(url).hostname or "invalid"
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError, ValueError:
        return "invalid"
    return _trace_text(ascii_hostname, 64) or "invalid"


def _trace_text(value: str, maximum: int) -> str:
    normalized = _normalize_single_line(value, maximum)
    return normalized.replace(" ", "_") or "unknown"


__all__ = [
    "AddressResolver",
    "BraveSearchProvider",
    "DDGSSearchProvider",
    "FetchErrorCode",
    "HttpxSafePageFetcher",
    "InvocationCitationRegistry",
    "SafePageFetchError",
    "SearchErrorCode",
    "TavilySearchProvider",
    "WebSearchError",
    "build_web_tools",
    "create_web_search_provider",
    "resolve_card_urls",
]
