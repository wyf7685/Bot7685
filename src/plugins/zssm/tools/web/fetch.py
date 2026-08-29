import codecs
import hashlib
import socket
import zlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from functools import partial
from time import monotonic
from typing import Literal, Self, cast
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import anyio
import httpx
from anyio.to_thread import run_sync
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.service.llm import BoundTool, JSONValue, ToolOutput

from ...config import FetchPageConfig
from ...contracts._validation import _nonempty
from ...contracts.web import (
    CitationRegistry,
    MediaSetRef,
    SafePageFetcher,
    WebPageResult,
)
from ...http_transport import (
    AddressResolver,
    DNSResolutionError,
    InvalidHttpTargetError,
    InvalidResponseHeaderError,
    IPAddress,
    PeerMismatchError,
    ResponseTooLargeError,
    UnsafeAddressError,
    ValidatedHttpTarget,
    build_pinned_request,
    close_response_bounded,
    read_bounded_body,
    resolve_public_addresses,
    validate_http_target,
    verify_peer,
)
from .citations import InvocationCitationRegistry
from .citations import citation_json as _citation_json
from .media import InvocationMediaRegistry
from .sources.contracts import DownloadedPage as _DownloadedPage
from .sources.contracts import ExtractedPage as _ExtractedPage
from .sources.contracts import SourceAdapterError
from .sources.registry import DEFAULT_SOURCE_REGISTRY, SourceRegistry
from .text import normalize_page_text as _normalize_page_text
from .text import normalize_single_line as _normalize_single_line
from .text import optional_metadata as _optional_metadata

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_USER_AGENT = "Bot7685-ZSSM/1.0"
_ROBOTS_CACHE_SECONDS = 300.0

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


type _RobotsMode = Literal["enforce", "skip"]


class FetchPageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _nonempty(value, "url")


@dataclass(frozen=True, slots=True)
class FetchPageToolContext:
    page_fetcher: SafePageFetcher = field(repr=False, compare=False)
    citation_registry: CitationRegistry = field(repr=False, compare=False)


class SafePageFetchError(RuntimeError):
    """A safe-fetch failure that never embeds a URL, body, or transport message."""

    def __init__(self, code: FetchErrorCode, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


def _validate_target(url: str) -> ValidatedHttpTarget:
    try:
        return validate_http_target(url)
    except InvalidHttpTargetError:
        raise SafePageFetchError("unsafe_url") from None


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
        media_registry: InvocationMediaRegistry | None = None,
    ) -> None:
        self._config = config
        self._citations = citation_registry
        self._resolver = resolver or _resolve_system_addresses
        self._clock = clock
        self._source_registry = source_registry or DEFAULT_SOURCE_REGISTRY
        self._media_registry = media_registry
        self._robots_cache: dict[tuple[str, bool], _RobotsCacheEntry] = {}
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
        self._source_client: httpx.AsyncClient | None = None
        if self._config.source_proxy is not None:
            self._source_client = httpx.AsyncClient(
                proxy=self._config.source_proxy.get_secret_value(),
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(None),
                http1=True,
                http2=False,
                limits=httpx.Limits(max_keepalive_connections=0),
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
        if self._source_client is not None:
            await self._source_client.aclose()
        await self._client.aclose()

    async def download(
        self,
        url: str,
        *,
        accept: str,
        allowed_content_types: Sequence[str],
    ) -> _DownloadedPage:
        try:
            with anyio.fail_after(self._config.total_timeout_seconds):
                return await self._download(
                    url,
                    allow_http_errors=False,
                    robots_mode=("enforce" if self._config.respect_robots else "skip"),
                    accept=accept,
                    allowed_content_types=allowed_content_types,
                    source_proxy=self._source_client is not None,
                )
        except TimeoutError:
            raise SafePageFetchError("timeout") from None

    async def download_media(
        self,
        url: str,
        *,
        referer: str,
        allowed_hosts: frozenset[str],
        max_bytes: int,
    ) -> _DownloadedPage:
        if max_bytes <= 0 or not allowed_hosts:
            raise SafePageFetchError("unsafe_url")
        normalized_hosts = frozenset(
            host.casefold().rstrip(".") for host in allowed_hosts
        )
        target = _validate_target(url)
        if target.hostname not in normalized_hosts:
            raise SafePageFetchError("unsafe_url")
        normalized_referer = _validate_target(referer).url
        try:
            with anyio.fail_after(self._config.total_timeout_seconds):
                return await self._download(
                    target.url,
                    allow_http_errors=False,
                    robots_mode="skip",
                    accept="image/jpeg,image/png,image/webp",
                    accept_encoding="identity",
                    allowed_content_types=("image/jpeg", "image/png", "image/webp"),
                    source_proxy=self._source_client is not None,
                    max_wire_bytes=max_bytes,
                    max_decoded_bytes=max_bytes,
                    referer=normalized_referer,
                    allowed_hosts=normalized_hosts,
                )
        except TimeoutError:
            raise SafePageFetchError("timeout") from None

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
                    request = _build_direct_request(
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
                        _verify_expected_peer(response, addresses)
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
                            await close_response_bounded(response)
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
                        media = (
                            self._media_registry.register(
                                adapter=adapter,
                                target=source_target,
                                count=specialized.media_count,
                                restricted=specialized.media_restricted,
                            )
                            if self._media_registry is not None
                            and specialized.media_count > 0
                            else None
                        )
                        return self._make_page_result(
                            requested_url=initial.url,
                            final_url=specialized.final_url,
                            extracted=specialized.extracted,
                            media=media,
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
        media: MediaSetRef | None = None,
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
            media=media,
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
        source_proxy: bool = False,
        max_wire_bytes: int | None = None,
        max_decoded_bytes: int | None = None,
        referer: str | None = None,
        allowed_hosts: frozenset[str] | None = None,
    ) -> _DownloadedPage:
        current = _validate_target(url)
        redirects = 0
        use_source_proxy = source_proxy and self._source_client is not None
        wire_limit = max_wire_bytes or self._config.max_wire_bytes
        decoded_limit = max_decoded_bytes or self._config.max_decoded_bytes
        if wire_limit <= 0 or decoded_limit <= 0:
            raise SafePageFetchError("too_large")
        while True:
            if allowed_hosts is not None and current.hostname not in allowed_hosts:
                raise SafePageFetchError("unsafe_url")
            if robots_mode == "enforce":
                await self._enforce_robots(
                    current,
                    source_proxy=use_source_proxy,
                )
            addresses = await self._resolve(current.hostname, current.port)
            if use_source_proxy:
                request = _build_source_proxy_request(
                    current,
                    accept=accept,
                    accept_encoding=accept_encoding,
                    referer=referer,
                )
                client = self._source_client
            else:
                request = _build_direct_request(
                    current,
                    addresses[0],
                    accept=accept,
                    accept_encoding=accept_encoding,
                    referer=referer,
                )
                client = self._client
            response: httpx.Response | None = None
            try:
                try:
                    response = await client.send(
                        request,
                        stream=True,
                        follow_redirects=False,
                        auth=None,
                    )
                except httpx.TimeoutException:
                    raise SafePageFetchError("timeout") from None
                except httpx.HTTPError:
                    raise SafePageFetchError("network") from None

                if not use_source_proxy:
                    _verify_expected_peer(response, addresses)
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
                wire = await self._read_wire_body(response, wire_limit)
                encoding = self._content_encoding(response.headers)
                body = _decode_content(
                    wire,
                    encoding=encoding,
                    max_decoded_bytes=decoded_limit,
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
                    await close_response_bounded(response)

    async def _resolve(self, hostname: str, port: int) -> tuple[IPAddress, ...]:
        try:
            addresses = await resolve_public_addresses(
                hostname,
                port,
                self._resolver,
            )
        except DNSResolutionError:
            raise SafePageFetchError("dns") from None
        except UnsafeAddressError:
            raise SafePageFetchError("unsafe_url") from None
        return tuple(sorted(addresses, key=lambda item: (item.version, item.packed)))

    async def _read_wire_body(
        self,
        response: httpx.Response,
        limit: int,
    ) -> bytes:
        try:
            return await read_bounded_body(response, limit)
        except ResponseTooLargeError, InvalidResponseHeaderError:
            raise SafePageFetchError("too_large") from None
        except httpx.TimeoutException:
            raise SafePageFetchError("timeout") from None
        except httpx.HTTPError:
            raise SafePageFetchError("network") from None

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

    async def _enforce_robots(
        self,
        target: ValidatedHttpTarget,
        *,
        source_proxy: bool = False,
    ) -> None:
        now = self._clock()
        cache_key = (target.origin, source_proxy)
        cached = self._robots_cache.get(cache_key)
        if cached is None or cached.expires_at <= now:
            cached = await self._load_robots(
                target,
                now,
                source_proxy=source_proxy,
            )
            self._robots_cache[cache_key] = cached

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
        target: ValidatedHttpTarget,
        now: float,
        *,
        source_proxy: bool,
    ) -> _RobotsCacheEntry:
        expires_at = now + _ROBOTS_CACHE_SECONDS
        robots_url = f"{target.origin}/robots.txt"
        try:
            downloaded = await self._download(
                robots_url,
                allow_http_errors=True,
                robots_mode="skip",
                accept_encoding="identity",
                source_proxy=source_proxy,
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


def build_fetch_page_tool(
    context: FetchPageToolContext,
) -> BoundTool[FetchPageToolContext, FetchPageArgs]:
    """Bind the safe page fetcher to one invocation context."""

    return BoundTool(
        name="fetch_page",
        description=(
            "Safely fetch and extract an HTTP or HTTPS page. The result includes a "
            "stable citation ID that should be referenced when used in the answer."
        ),
        arguments_type=FetchPageArgs,
        context=context,
        handler=_handle_fetch_page,
    )


async def _handle_fetch_page(
    context: FetchPageToolContext,
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


async def _resolve_system_addresses(hostname: str, port: int) -> Sequence[str]:
    infos = await anyio.getaddrinfo(
        hostname,
        port,
        family=socket.AF_UNSPEC,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(str(info[4][0]) for info in infos)


def _request_headers(
    *,
    accept: str,
    accept_encoding: str,
    referer: str | None,
) -> dict[str, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": accept,
        "Accept-Encoding": accept_encoding,
    }
    if referer is not None:
        headers["Referer"] = referer
    return headers


def _build_source_proxy_request(
    target: ValidatedHttpTarget,
    *,
    accept: str,
    accept_encoding: str,
    referer: str | None = None,
) -> httpx.Request:
    return httpx.Request(
        "GET",
        target.url,
        headers=_request_headers(
            accept=accept,
            accept_encoding=accept_encoding,
            referer=referer,
        ),
    )


def _build_direct_request(
    target: ValidatedHttpTarget,
    address: IPAddress,
    *,
    method: Literal["GET", "HEAD"] = "GET",
    accept: str = "text/html,application/xhtml+xml,text/plain,text/markdown",
    accept_encoding: str = "gzip, deflate",
    referer: str | None = None,
) -> httpx.Request:
    return build_pinned_request(
        target,
        address,
        method=method,
        headers=_request_headers(
            accept=accept,
            accept_encoding=accept_encoding,
            referer=referer,
        ),
    )


def _verify_expected_peer(
    response: httpx.Response, expected: Sequence[IPAddress]
) -> None:
    try:
        verify_peer(response, expected)
    except PeerMismatchError:
        raise SafePageFetchError("peer_mismatch") from None


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


def _plain_text_title(text: str, hostname: str, media_type: str | None) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if media_type == "text/markdown":
        first_line = first_line.lstrip("#").strip()
    return _normalize_single_line(first_line, 500) or hostname


def _web_page_json(page: WebPageResult) -> dict[str, JSONValue]:
    value: dict[str, JSONValue] = {
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
    if page.media is not None:
        value["media"] = {
            "media_id": page.media.media_id,
            "kind": "image_collection",
            "count": page.media.count,
            "restricted": page.media.restricted,
        }
    return value


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
    "FetchErrorCode",
    "FetchPageToolContext",
    "HttpxSafePageFetcher",
    "SafePageFetchError",
    "build_fetch_page_tool",
    "resolve_card_urls",
]
