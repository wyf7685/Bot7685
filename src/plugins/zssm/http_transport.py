import ipaddress
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

import anyio
import httpx

_DEFAULT_PORTS = {"http": 80, "https": 443}
_MAX_URL_CHARS = 4096
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
type AddressResolver = Callable[[str, int], Awaitable[Sequence[str]]]


class InvalidHttpTargetError(ValueError):
    """The URL is outside the accepted public HTTP(S) syntax policy."""


class DNSResolutionError(RuntimeError):
    """The hostname could not be resolved to usable addresses."""


class UnsafeAddressError(RuntimeError):
    """A resolved address is ambiguous or outside the public Internet."""


class PeerMismatchError(RuntimeError):
    """The connected peer does not match the prevalidated address set."""


class ResponseTooLargeError(RuntimeError):
    """The response body exceeds its configured wire-size limit."""


class InvalidResponseHeaderError(RuntimeError):
    """A security-relevant response header is malformed or ambiguous."""


@dataclass(frozen=True, slots=True)
class ValidatedHttpTarget:
    url: str
    scheme: Literal["http", "https"]
    hostname: str
    port: int
    origin: str
    host_header: str


def normalize_http_url(url: str) -> str:
    return validate_http_target(url).url


def validate_http_target(url: str) -> ValidatedHttpTarget:
    if not isinstance(url, str):
        raise InvalidHttpTargetError
    url = url.strip()
    if (
        not url
        or len(url) > _MAX_URL_CHARS
        or any(ord(character) < 32 for character in url)
    ):
        raise InvalidHttpTargetError
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise InvalidHttpTargetError from None
    scheme = parsed.scheme.casefold()
    if (
        scheme not in _DEFAULT_PORTS
        or not parsed.netloc
        or parsed.netloc.endswith(":")
        or "\\" in parsed.netloc
    ):
        raise InvalidHttpTargetError
    if parsed.username is not None or parsed.password is not None:
        raise InvalidHttpTargetError
    hostname = parsed.hostname
    if hostname is None:
        raise InvalidHttpTargetError
    hostname = hostname.rstrip(".")
    if not hostname:
        raise InvalidHttpTargetError
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidHttpTargetError
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except UnicodeError, ValueError:
        raise InvalidHttpTargetError from None
    if len(ascii_hostname) > 253 or any(
        not _HOST_LABEL_RE.fullmatch(label) for label in ascii_hostname.split(".")
    ):
        raise InvalidHttpTargetError
    if port != _DEFAULT_PORTS[scheme]:
        raise InvalidHttpTargetError

    path = parsed.path or "/"
    canonical = SplitResult(scheme, ascii_hostname, path, parsed.query, "")
    normalized_url = urlunsplit(canonical)
    origin = f"{scheme}://{ascii_hostname}"
    return ValidatedHttpTarget(
        url=normalized_url,
        scheme=cast("Literal['http', 'https']", scheme),
        hostname=ascii_hostname,
        port=port,
        origin=origin,
        host_header=ascii_hostname,
    )


def is_unambiguous_global(address: IPAddress) -> bool:
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


async def resolve_public_addresses(
    hostname: str,
    port: int,
    resolver: AddressResolver,
    *,
    maximum: int | None = None,
) -> tuple[IPAddress, ...]:
    if maximum is not None and maximum <= 0:
        raise ValueError("maximum address count must be positive")
    try:
        raw_addresses = await resolver(hostname, port)
    except Exception:
        raise DNSResolutionError from None

    addresses: list[IPAddress] = []
    seen: set[IPAddress] = set()
    for raw_address in raw_addresses:
        if not isinstance(raw_address, str) or "%" in raw_address:
            raise UnsafeAddressError
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError:
            raise DNSResolutionError from None
        if not is_unambiguous_global(address):
            raise UnsafeAddressError
        if address in seen:
            continue
        seen.add(address)
        addresses.append(address)
    if not addresses:
        raise DNSResolutionError
    return tuple(addresses if maximum is None else addresses[:maximum])


def build_pinned_request(
    target: ValidatedHttpTarget,
    address: IPAddress,
    *,
    method: Literal["GET", "HEAD"] = "GET",
    headers: Mapping[str, str] | None = None,
    timeout: Mapping[str, float] | None = None,
) -> httpx.Request:
    parsed = urlsplit(target.url)
    connect_host = f"[{address}]" if address.version == 6 else str(address)
    connect_url = urlunsplit(
        (target.scheme, connect_host, parsed.path, parsed.query, "")
    )
    extensions: dict[str, Any] = {}
    if target.scheme == "https":
        extensions["sni_hostname"] = target.hostname
    if timeout is not None:
        extensions["timeout"] = dict(timeout)
    request_headers = dict(headers or ())
    request_headers["Host"] = target.host_header
    return httpx.Request(
        method,
        connect_url,
        headers=request_headers,
        extensions=extensions,
    )


def verify_peer(response: httpx.Response, expected: Sequence[IPAddress]) -> None:
    stream = response.extensions.get("network_stream")
    if stream is None or not hasattr(stream, "get_extra_info"):
        return
    peer = stream.get_extra_info("server_addr")
    if peer is None:
        return
    raw_address = peer[0] if isinstance(peer, tuple) and peer else peer
    if not isinstance(raw_address, str):
        raise PeerMismatchError
    try:
        actual = ipaddress.ip_address(raw_address.split("%", 1)[0])
    except ValueError:
        raise PeerMismatchError from None
    if actual not in expected or not is_unambiguous_global(actual):
        raise PeerMismatchError


async def read_bounded_body(response: httpx.Response, limit: int) -> bytes:
    if limit <= 0:
        raise ValueError("response body limit must be positive")
    lengths = response.headers.get_list("content-length")
    if len(lengths) > 1:
        raise InvalidResponseHeaderError
    if lengths:
        try:
            content_length = int(lengths[0])
        except ValueError:
            raise InvalidResponseHeaderError from None
        if content_length < 0:
            raise InvalidResponseHeaderError
        if content_length > limit:
            raise ResponseTooLargeError

    if response.is_stream_consumed:
        if len(response.content) > limit:
            raise ResponseTooLargeError
        return response.content

    body = bytearray()
    async for chunk in response.aiter_raw():
        if len(body) + len(chunk) > limit:
            raise ResponseTooLargeError
        body.extend(chunk)
    return bytes(body)


async def close_response_bounded(
    response: httpx.Response,
    *,
    close_timeout: float = 1.0,
) -> None:
    if close_timeout <= 0:
        raise ValueError("response close timeout must be positive")
    with anyio.move_on_after(close_timeout, shield=True):
        with suppress(Exception):
            await response.aclose()


__all__ = [
    "AddressResolver",
    "DNSResolutionError",
    "IPAddress",
    "InvalidHttpTargetError",
    "InvalidResponseHeaderError",
    "PeerMismatchError",
    "ResponseTooLargeError",
    "UnsafeAddressError",
    "ValidatedHttpTarget",
    "build_pinned_request",
    "close_response_bounded",
    "is_unambiguous_global",
    "normalize_http_url",
    "read_bounded_body",
    "resolve_public_addresses",
    "validate_http_target",
    "verify_peer",
]
