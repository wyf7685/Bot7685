import asyncio
import hashlib
import os
import socket
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.parse import urljoin

import httpx
from nonebot_plugin_alconna.uniseg import Image

from ..config import ImagesConfig
from ..contracts import (
    CollectedImageInput,
    ImageFailure,
    ImageFailureCategory,
    ImageFailureStage,
)
from ..http_transport import (
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

_CONNECT_TIMEOUT_SECONDS: Final = 5.0
_READ_TIMEOUT_SECONDS: Final = 15.0
_FETCH_DEADLINE_SECONDS: Final = 15.0
_RESPONSE_CLOSE_TIMEOUT_SECONDS: Final = 1.0
_MAX_ADDRESS_ATTEMPTS_PER_FETCH: Final = 8
_MAX_REDIRECTS: Final = 5
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})


type ImageURLResolver = AddressResolver


type AdapterImageFetcher = Callable[[Image], Awaitable[bytes | None]]


@dataclass(frozen=True, slots=True)
class _ResolvedImageTarget:
    target: ValidatedHttpTarget
    addresses: tuple[IPAddress, ...]


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
                try:
                    verify_peer(response, target.addresses)
                except PeerMismatchError:
                    raise _ImageDownloadError from None
                _validate_content_encoding(response)
                if response.status_code in _REDIRECT_STATUSES:
                    if redirect_count == _MAX_REDIRECTS or remaining_attempts <= 0:
                        raise _ImageDownloadError
                    location = response.headers.get("Location")
                    if not location:
                        raise _ImageDownloadError
                    try:
                        current = urljoin(target.target.url, location)
                    except (TypeError, ValueError) as error:
                        raise _SourceUnavailableError from error
                    continue
                if not 200 <= response.status_code < 300:
                    raise _ImageDownloadError
                return await _read_response_bounded(response, limit)
            finally:
                await close_response_bounded(
                    response,
                    close_timeout=_RESPONSE_CLOSE_TIMEOUT_SECONDS,
                )
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
            target = validate_http_target(segment.url)
        except InvalidHttpTargetError:
            return None
        return ("url", target.url)
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


async def _resolve_image_target(
    raw_url: str,
    resolver: ImageURLResolver,
    *,
    address_limit: int,
) -> _ResolvedImageTarget:
    try:
        target = validate_http_target(raw_url)
    except InvalidHttpTargetError:
        raise _SourceUnavailableError from None
    try:
        addresses = await resolve_public_addresses(
            target.hostname,
            target.port,
            resolver,
            maximum=address_limit,
        )
    except DNSResolutionError, UnsafeAddressError:
        raise _SourceUnavailableError from None
    return _ResolvedImageTarget(target=target, addresses=addresses)


async def _send_pinned_request(
    target: _ResolvedImageTarget,
    transport: httpx.AsyncBaseTransport,
) -> tuple[httpx.Response, int]:
    last_error: httpx.TransportError | None = None
    for attempts, address in enumerate(target.addresses, 1):
        request = build_pinned_request(
            target.target,
            address,
            headers={
                "Accept": "image/*",
                "Accept-Encoding": "identity",
                "User-Agent": "Bot7685-ZSSM-Image/1",
            },
            timeout={
                "connect": _CONNECT_TIMEOUT_SECONDS,
                "read": _READ_TIMEOUT_SECONDS,
                "write": _READ_TIMEOUT_SECONDS,
                "pool": _CONNECT_TIMEOUT_SECONDS,
            },
        )
        try:
            return await transport.handle_async_request(request), attempts
        except httpx.TransportError as error:
            last_error = error
    if last_error is not None:
        raise last_error
    raise _SourceUnavailableError


async def _read_response_bounded(response: httpx.Response, limit: int) -> bytes:
    _validate_content_encoding(response)
    try:
        return await read_bounded_body(response, limit)
    except ResponseTooLargeError:
        raise _SourceTooLargeError from None
    except InvalidResponseHeaderError:
        raise _ImageDownloadError from None


def _validate_content_encoding(response: httpx.Response) -> None:
    content_encoding = response.headers.get("Content-Encoding", "").strip().lower()
    if content_encoding and content_encoding != "identity":
        raise _ImageDownloadError


__all__ = ["AdapterImageFetcher", "ImageURLResolver"]
