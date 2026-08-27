import asyncio
import hashlib
import ipaddress
import os
import socket
from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import httpx
from nonebot_plugin_alconna.uniseg import Image

from ..config import ImagesConfig
from ..contracts import (
    CollectedImageInput,
    ImageFailure,
    ImageFailureCategory,
    ImageFailureStage,
)

_CONNECT_TIMEOUT_SECONDS: Final = 5.0
_READ_TIMEOUT_SECONDS: Final = 15.0
_FETCH_DEADLINE_SECONDS: Final = 15.0
_RESPONSE_CLOSE_TIMEOUT_SECONDS: Final = 1.0
_MAX_ADDRESS_ATTEMPTS_PER_FETCH: Final = 8
_MAX_REDIRECTS: Final = 5
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})


type ImageURLResolver = Callable[[str, int], Awaitable[Sequence[str]]]


type AdapterImageFetcher = Callable[[Image], Awaitable[bytes | None]]


@dataclass(frozen=True, slots=True)
class _ResolvedImageTarget:
    url: httpx.URL
    hostname: str
    host_header: str
    addresses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SafeImageFetcher:
    resolver: ImageURLResolver
    transport: httpx.AsyncBaseTransport = field(repr=False, compare=False)

    async def fetch(self, url: str, limit: int) -> bytes:
        fetch_task = asyncio.create_task(self._fetch(url, limit))
        try:
            async with asyncio.timeout(_FETCH_DEADLINE_SECONDS):
                return await asyncio.shield(fetch_task)
        except TimeoutError as error:
            fetch_task.cancel()
            await _await_fetch_cleanup(fetch_task)
            raise _ImageDownloadError from error
        except asyncio.CancelledError:
            fetch_task.cancel()
            await _await_fetch_cleanup(fetch_task)
            raise

    async def _fetch(self, url: str, limit: int) -> bytes:
        current = url
        remaining_attempts = _MAX_ADDRESS_ATTEMPTS_PER_FETCH
        for redirect_count in range(_MAX_REDIRECTS + 1):
            if remaining_attempts <= 0:
                raise _ImageDownloadError
            target = await _resolve_image_target(
                current,
                self.resolver,
                address_limit=remaining_attempts,
            )
            response, attempts = await _send_pinned_request(target, self.transport)
            remaining_attempts -= attempts
            try:
                _validate_content_encoding(response)
                if response.status_code in _REDIRECT_STATUSES:
                    if redirect_count == _MAX_REDIRECTS or remaining_attempts <= 0:
                        raise _ImageDownloadError
                    location = response.headers.get("Location")
                    if not location:
                        raise _ImageDownloadError
                    try:
                        current = str(target.url.join(location))
                    except (httpx.InvalidURL, ValueError) as error:
                        raise _SourceUnavailableError from error
                    continue
                if not 200 <= response.status_code < 300:
                    raise _ImageDownloadError
                return await _read_response_bounded(response, limit)
            finally:
                await _close_response_bounded(response)
        raise _ImageDownloadError


async def _await_fetch_cleanup(fetch_task: asyncio.Task[bytes]) -> None:
    try:
        async with asyncio.timeout(_RESPONSE_CLOSE_TIMEOUT_SECONDS + 0.1):
            await asyncio.shield(fetch_task)
    except TimeoutError:
        fetch_task.cancel()
        fetch_task.add_done_callback(_consume_task_result)
    except asyncio.CancelledError:
        if not fetch_task.done():
            fetch_task.add_done_callback(_consume_task_result)
            raise
    except Exception:
        return


async def _close_response_bounded(response: httpx.Response) -> None:
    close_task = asyncio.create_task(response.aclose())
    try:
        async with asyncio.timeout(_RESPONSE_CLOSE_TIMEOUT_SECONDS):
            await asyncio.shield(close_task)
    except TimeoutError:
        close_task.cancel()
        close_task.add_done_callback(_consume_task_result)
    except asyncio.CancelledError:
        close_task.cancel()
        close_task.add_done_callback(_consume_task_result)
        raise
    except Exception:
        return


def _consume_task_result(task: asyncio.Task[object]) -> None:
    with suppress(BaseException):
        task.result()


@dataclass(frozen=True, slots=True)
class _AcquiredImage:
    collected: CollectedImageInput = field(repr=False)
    data: bytes = field(repr=False)
    sha256: str


class _SourceTooLargeError(Exception):
    pass


class _SourceUnavailableError(Exception):
    pass


class _ImageDownloadError(Exception):
    pass


class _InvalidImageError(Exception):
    pass


def _deduplicate_source_references(
    images: tuple[CollectedImageInput, ...],
) -> tuple[CollectedImageInput, ...]:
    seen_ids: set[str] = set()
    seen_locations: set[tuple[str, str]] = set()
    unique: list[CollectedImageInput] = []
    for image in images:
        segment = image.segment
        opaque_id = str(segment.id).strip() if segment.id is not None else ""
        if opaque_id and opaque_id in seen_ids:
            continue
        location = _source_location_key(segment)
        if location is not None and location in seen_locations:
            continue
        if opaque_id:
            seen_ids.add(opaque_id)
        if location is not None:
            seen_locations.add(location)
        unique.append(image)
    return tuple(unique)


def _source_location_key(segment: Image) -> tuple[str, str] | None:
    if segment.raw is not None:
        return None
    if segment.path is not None:
        path = os.path.normcase(str(Path(segment.path).resolve()))
        return ("path", path)
    if segment.url:
        try:
            normalized_url, _, _, _ = _normalize_image_url(segment.url)
        except _SourceUnavailableError:
            return None
        return ("url", str(normalized_url))
    return None


def _uses_url_source(
    segment: Image,
    adapter_image_fetcher: AdapterImageFetcher | None,
) -> bool:
    return (
        segment.raw is None
        and segment.path is None
        and bool(segment.url)
        and not (segment.id and adapter_image_fetcher is not None)
    )


async def _acquire_all(
    images: tuple[CollectedImageInput, ...],
    config: ImagesConfig,
    fetcher: _SafeImageFetcher | None,
    adapter_image_fetcher: AdapterImageFetcher | None,
) -> list[_AcquiredImage | ImageFailure]:
    semaphore = asyncio.Semaphore(config.max_parallel)
    outcomes: list[_AcquiredImage | ImageFailure | None] = [None] * len(images)

    async def acquire_one(index: int, image: CollectedImageInput) -> None:
        async with semaphore:
            outcomes[index] = await _acquire_outcome(
                image,
                config,
                fetcher,
                adapter_image_fetcher,
            )

    async with asyncio.TaskGroup() as tasks:
        for index, image in enumerate(images):
            tasks.create_task(acquire_one(index, image))
    return [outcome for outcome in outcomes if outcome is not None]


async def _acquire_outcome(
    image: CollectedImageInput,
    config: ImagesConfig,
    fetcher: _SafeImageFetcher | None,
    adapter_image_fetcher: AdapterImageFetcher | None,
) -> _AcquiredImage | ImageFailure:
    try:
        data = await _read_image_source(
            image.segment,
            config.max_source_bytes,
            fetcher,
            adapter_image_fetcher,
        )
        if not data:
            raise _InvalidImageError
        digest = hashlib.sha256(data).hexdigest()
        return _AcquiredImage(collected=image, data=data, sha256=digest)
    except _SourceTooLargeError:
        category = ImageFailureCategory.TOO_LARGE
    except httpx.TransportError, _ImageDownloadError:
        category = ImageFailureCategory.DOWNLOAD
    except _InvalidImageError:
        category = ImageFailureCategory.INVALID
    except OSError, _SourceUnavailableError, ValueError, TypeError:
        category = ImageFailureCategory.UNAVAILABLE
    return ImageFailure(
        label=image.label,
        stage=ImageFailureStage.ACQUISITION,
        category=category,
    )


async def _read_image_source(
    segment: Image,
    limit: int,
    fetcher: _SafeImageFetcher | None,
    adapter_image_fetcher: AdapterImageFetcher | None,
) -> bytes:
    if segment.raw is not None:
        if isinstance(segment.raw, BytesIO):
            view = segment.raw.getbuffer()
            try:
                if len(view) > limit:
                    raise _SourceTooLargeError
                return bytes(view)
            finally:
                view.release()
        if not isinstance(segment.raw, bytes):
            raise _InvalidImageError
        if len(segment.raw) > limit:
            raise _SourceTooLargeError
        return segment.raw
    if segment.path is not None:
        return await asyncio.to_thread(_read_path_bounded, Path(segment.path), limit)
    if segment.id and adapter_image_fetcher is not None:
        try:
            adapter_data = await adapter_image_fetcher(segment)
        except Exception as error:
            raise _ImageDownloadError from error
        if adapter_data is not None:
            if len(adapter_data) > limit:
                raise _SourceTooLargeError
            return adapter_data
    if segment.url:
        if fetcher is None:
            raise _SourceUnavailableError
        return await fetcher.fetch(segment.url, limit)
    raise _SourceUnavailableError


def _read_path_bounded(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise _SourceTooLargeError
    return data


async def _resolve_global_addresses(hostname: str, port: int) -> tuple[str, ...]:
    records = await asyncio.get_running_loop().getaddrinfo(
        hostname,
        port,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP,
    )
    return tuple(dict.fromkeys(str(record[4][0]) for record in records))


def _normalize_image_url(raw_url: str) -> tuple[httpx.URL, str, int, str]:
    try:
        parsed = urlsplit(raw_url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname
        explicit_port = parsed.port
    except (UnicodeError, ValueError) as error:
        raise _SourceUnavailableError from error
    if (
        scheme not in {"http", "https"}
        or not hostname
        or parsed.netloc.endswith(":")
        or parsed.path.startswith("//")
    ):
        raise _SourceUnavailableError
    if parsed.username is not None or parsed.password is not None:
        raise _SourceUnavailableError
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise _SourceUnavailableError

    default_port = 443 if scheme == "https" else 80
    if explicit_port is not None and explicit_port != default_port:
        raise _SourceUnavailableError
    try:
        normalized_url = httpx.URL(raw_url).copy_with(fragment=None)
        ascii_hostname = normalized_url.raw_host.decode("ascii")
        if explicit_port is not None:
            normalized_url = normalized_url.copy_with(port=None)
    except (httpx.InvalidURL, UnicodeError, ValueError) as error:
        raise _SourceUnavailableError from error
    host_header = (
        ascii_hostname if explicit_port is None else f"{ascii_hostname}:{default_port}"
    )
    return normalized_url, ascii_hostname, default_port, host_header


async def _resolve_image_target(
    raw_url: str,
    resolver: ImageURLResolver,
    *,
    address_limit: int,
) -> _ResolvedImageTarget:
    normalized_url, ascii_hostname, default_port, host_header = _normalize_image_url(
        raw_url
    )
    try:
        resolved = await resolver(ascii_hostname, default_port)
    except (UnicodeError, ValueError) as error:
        raise _SourceUnavailableError from error

    addresses: list[str] = []
    seen_addresses: set[str] = set()
    for raw_address in resolved:
        if not isinstance(raw_address, str) or "%" in raw_address:
            raise _SourceUnavailableError
        try:
            address = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise _SourceUnavailableError from error
        if not _is_global_unicast(address):
            raise _SourceUnavailableError
        normalized_address = address.compressed
        if normalized_address in seen_addresses:
            continue
        seen_addresses.add(normalized_address)
        if len(addresses) < address_limit:
            addresses.append(normalized_address)
    if not addresses:
        raise _SourceUnavailableError
    return _ResolvedImageTarget(
        url=normalized_url,
        hostname=ascii_hostname,
        host_header=host_header,
        addresses=tuple(addresses),
    )


def _is_global_unicast(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_private
        and not address.is_reserved
        and not getattr(address, "is_site_local", False)
    )


async def _send_pinned_request(
    target: _ResolvedImageTarget,
    transport: httpx.AsyncBaseTransport,
) -> tuple[httpx.Response, int]:
    last_error: httpx.TransportError | None = None
    for attempts, address in enumerate(target.addresses, 1):
        request = httpx.Request(
            "GET",
            target.url.copy_with(host=address),
            headers={
                "Host": target.host_header,
                "Accept": "image/*",
                "Accept-Encoding": "identity",
                "User-Agent": "Bot7685-ZSSM-Image/1",
            },
            extensions={
                "sni_hostname": target.hostname,
                "timeout": {
                    "connect": _CONNECT_TIMEOUT_SECONDS,
                    "read": _READ_TIMEOUT_SECONDS,
                    "write": _READ_TIMEOUT_SECONDS,
                    "pool": _CONNECT_TIMEOUT_SECONDS,
                },
            },
        )
        try:
            return await transport.handle_async_request(request), attempts
        except httpx.TransportError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise _SourceUnavailableError


def _validate_content_encoding(response: httpx.Response) -> None:
    content_encoding = response.headers.get("Content-Encoding", "").strip().lower()
    if content_encoding and content_encoding != "identity":
        raise _ImageDownloadError


async def _read_response_bounded(response: httpx.Response, limit: int) -> bytes:
    _validate_content_encoding(response)
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise _SourceTooLargeError
        except ValueError:
            pass
    data = bytearray()
    async for chunk in response.aiter_raw():
        if len(data) + len(chunk) > limit:
            raise _SourceTooLargeError
        data.extend(chunk)
    return bytes(data)


__all__ = ["AdapterImageFetcher", "ImageURLResolver"]
