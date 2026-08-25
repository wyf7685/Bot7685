from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import math
import os
import re
import socket
import warnings
from collections.abc import Awaitable, Callable, Iterable, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import httpx
from nonebot_plugin_alconna.uniseg import (
    At,
    AtAll,
    Audio,
    Emoji,
    File,
    Hyper,
    Image,
    Keyboard,
    Reference,
    Reply,
    Segment,
    Text,
    UniMessage,
    Video,
    Voice,
)
from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from src.service.llm import ImagePart, TextPart

from .config import ImagesConfig
from .contracts import (
    CollectedImageInput,
    CollectedInput,
    ImageFailure,
    ImageFailureCategory,
    ImageFailureStage,
    ImageStageStatistics,
    InputLocation,
    NormalizedImage,
    ParticipantResolver,
    PreparedImage,
)

_CONNECT_TIMEOUT_SECONDS: Final = 5.0
_READ_TIMEOUT_SECONDS: Final = 15.0
_FETCH_DEADLINE_SECONDS: Final = 15.0
_RESPONSE_CLOSE_TIMEOUT_SECONDS: Final = 1.0
_MAX_ADDRESS_ATTEMPTS_PER_FETCH: Final = 8
_MAX_REDIRECTS: Final = 5
_REDIRECT_STATUSES: Final = frozenset({301, 302, 303, 307, 308})
_DATA_URL_PREFIX: Final = "data:image/jpeg;base64,"
_PLACEHOLDER_TYPE_RE: Final = re.compile(r"[^a-z0-9_-]+")
_MEDIA_PLACEHOLDERS: Final[dict[type[Segment], str]] = {
    Audio: "[audio]",
    Voice: "[voice]",
    Video: "[video]",
    File: "[file]",
}

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


class InputCollectionError(ValueError):
    """A safe, user-correctable input collection failure."""


class EmptyInputError(InputCollectionError):
    """The invocation contains no substantive text or media."""


class UnsupportedInputError(InputCollectionError):
    """The invocation contains a segment that cannot be flattened safely."""


class ImageLimitError(InputCollectionError):
    """The invocation contains more images than configured."""


@dataclass(frozen=True, slots=True)
class ImagePreparationResult:
    images: tuple[PreparedImage, ...]
    failures: tuple[ImageFailure, ...]
    statistics: ImageStageStatistics

    def __post_init__(self) -> None:
        object.__setattr__(self, "images", tuple(self.images))
        object.__setattr__(self, "failures", tuple(self.failures))
        if len(self.images) != self.statistics.prepared:
            raise ValueError("prepared image count does not match statistics")
        if len(self.failures) != self.statistics.acquisition_failed:
            raise ValueError("image failure count does not match statistics")


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


def collect_input(
    current: UniMessage,
    quoted: UniMessage | None,
    *,
    invoker_raw_id: str,
    participant_resolver: ParticipantResolver,
    config: ImagesConfig,
) -> CollectedInput:
    """Collect a stable, model-safe snapshot without performing image I/O."""

    if not isinstance(current, UniMessage):
        raise TypeError("current must be a UniMessage")
    if quoted is not None and not isinstance(quoted, UniMessage):
        raise TypeError("quoted must be a UniMessage or None")
    if not invoker_raw_id:
        raise InputCollectionError("invoker ID must not be empty")

    current_snapshot = current.copy()
    quoted_snapshot = quoted.copy() if quoted is not None else None
    ordered_messages = tuple(
        (location, message)
        for location, message in (
            (InputLocation.QUOTED, quoted_snapshot),
            (InputLocation.CURRENT, current_snapshot),
        )
        if message is not None
    )

    for _, message in ordered_messages:
        for segment in _walk_segments(message):
            if isinstance(segment, Reference):
                raise UnsupportedInputError(
                    "forwarded or nested references are unsupported"
                )

    invoker = participant_resolver.observe(invoker_raw_id, is_invoker=True)
    participant_aliases = [invoker.participant_alias]
    seen_aliases = {invoker.participant_alias}
    images: list[CollectedImageInput] = []
    rendered: dict[InputLocation, str] = {}
    substantive = False
    source_index = 0

    for location, message in ordered_messages:
        fragments: list[str] = []
        for segment in message:
            if isinstance(segment, Text):
                fragments.append(segment.text)
                substantive = substantive or bool(segment.text.strip())
            elif isinstance(segment, At) and segment.flag == "user":
                participant = participant_resolver.observe(str(segment.target))
                alias = participant.participant_alias
                fragments.append(f"<participant:{alias}>")
                if alias not in seen_aliases:
                    seen_aliases.add(alias)
                    participant_aliases.append(alias)
            elif isinstance(segment, Image):
                images.append(
                    CollectedImageInput(
                        label=f"image-{len(images) + 1}",
                        location=location,
                        source_index=source_index,
                        segment=segment,
                    )
                )
                substantive = True
            elif isinstance(segment, Reply):
                pass
            else:
                fragments.append(_safe_placeholder(segment))
                substantive = substantive or not isinstance(segment, (At, AtAll))
            source_index += 1
        rendered[location] = "".join(fragments)
    if len(_deduplicate_source_references(tuple(images))) > config.max_count:
        raise ImageLimitError(f"at most {config.max_count} unique images are allowed")

    if not substantive:
        raise EmptyInputError("input must contain text or supported media")

    quoted_text = rendered.get(InputLocation.QUOTED, "")
    current_text = rendered.get(InputLocation.CURRENT, "")
    prompt_parts_list: list[TextPart] = []
    if quoted_snapshot is not None:
        quoted_prompt = "Quoted message:"
        if quoted_text:
            quoted_prompt += f"\n{quoted_text}"
        prompt_parts_list.append(TextPart(quoted_prompt))
        if current_text:
            prompt_parts_list.append(TextPart(f"Current supplement:\n{current_text}"))
    elif current_text:
        prompt_parts_list.append(TextPart(current_text))
    prompt_parts = tuple(prompt_parts_list)
    prompt_text = "\n\n".join(part.text for part in prompt_parts)
    return CollectedInput(
        prompt_text=prompt_text,
        prompt_parts=prompt_parts,
        current=current_snapshot,
        quoted=quoted_snapshot,
        images=tuple(images),
        participant_aliases=tuple(participant_aliases),
    )


async def prepare_images(
    collected: CollectedInput,
    *,
    config: ImagesConfig,
    adapter_image_fetcher: AdapterImageFetcher | None = None,
    url_resolver: ImageURLResolver | None = None,
    url_transport: httpx.AsyncBaseTransport | None = None,
) -> ImagePreparationResult:
    """Acquire, deduplicate, and normalize collected images in stable order."""

    requested = len(collected.images)
    if not collected.images:
        return ImagePreparationResult(
            images=(),
            failures=(),
            statistics=ImageStageStatistics(),
        )

    candidates = _deduplicate_source_references(collected.images)
    if len(candidates) > config.max_count:
        raise ImageLimitError(f"at most {config.max_count} unique images are allowed")
    needs_http = any(
        _uses_url_source(item.segment, adapter_image_fetcher) for item in candidates
    )
    if needs_http:
        owned_transport = url_transport is None
        active_transport = url_transport or httpx.AsyncHTTPTransport(
            trust_env=False,
            http1=True,
            http2=False,
            retries=0,
            limits=httpx.Limits(
                max_connections=config.max_parallel,
                max_keepalive_connections=0,
            ),
        )
        fetcher = _SafeImageFetcher(
            resolver=url_resolver or _resolve_global_addresses,
            transport=active_transport,
        )
        try:
            acquired_outcomes = await _acquire_all(
                candidates,
                config,
                fetcher,
                adapter_image_fetcher,
            )
        finally:
            if owned_transport:
                await active_transport.aclose()
    else:
        acquired_outcomes = await _acquire_all(
            candidates,
            config,
            None,
            adapter_image_fetcher,
        )

    unique_acquired: list[_AcquiredImage] = []
    failures: list[ImageFailure] = []
    seen_content: set[str] = set()
    unique_count = 0
    for _candidate, outcome in zip(candidates, acquired_outcomes, strict=True):
        if isinstance(outcome, ImageFailure):
            unique_count += 1
            failures.append(outcome)
            continue
        if outcome.sha256 in seen_content:
            continue
        seen_content.add(outcome.sha256)
        unique_count += 1
        unique_acquired.append(outcome)

    normalized_outcomes = await _normalize_all(unique_acquired, config)
    prepared: list[PreparedImage] = []
    for outcome in normalized_outcomes:
        if isinstance(outcome, ImageFailure):
            failures.append(outcome)
        else:
            prepared.append(_to_prepared_image(outcome))

    statistics = ImageStageStatistics(
        requested=requested,
        unique=unique_count,
        prepared=len(prepared),
        acquisition_failed=len(failures),
    )
    return ImagePreparationResult(
        images=tuple(prepared),
        failures=tuple(failures),
        statistics=statistics,
    )


def _walk_segments(segments: Iterable[Segment]) -> Iterable[Segment]:
    for segment in segments:
        yield segment
        children = getattr(segment, "children", ())
        nested = tuple(child for child in children if isinstance(child, Segment))
        if nested:
            yield from _walk_segments(nested)


def _safe_placeholder(segment: Segment) -> str:
    if isinstance(segment, At):
        return f"[mention-{segment.flag}]"
    if isinstance(segment, AtAll):
        return "[mention-all]"
    if isinstance(segment, Emoji):
        return "[emoji]"
    for segment_type, placeholder in _MEDIA_PLACEHOLDERS.items():
        if isinstance(segment, segment_type):
            return placeholder
    if isinstance(segment, Hyper):
        return "[card]"
    if isinstance(segment, Keyboard):
        return "[interactive]"
    type_name = _PLACEHOLDER_TYPE_RE.sub("-", segment.type.lower()).strip("-")[:32]
    return f"[{type_name or "segment"}]"


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


async def _normalize_all(
    images: list[_AcquiredImage],
    config: ImagesConfig,
) -> list[NormalizedImage | ImageFailure]:
    semaphore = asyncio.Semaphore(config.max_parallel)
    outcomes: list[NormalizedImage | ImageFailure | None] = [None] * len(images)

    async def normalize_one(index: int, image: _AcquiredImage) -> None:
        async with semaphore:
            outcomes[index] = await _normalize_outcome(image, config)

    async with asyncio.TaskGroup() as tasks:
        for index, image in enumerate(images):
            tasks.create_task(normalize_one(index, image))
    return [outcome for outcome in outcomes if outcome is not None]


async def _normalize_outcome(
    image: _AcquiredImage,
    config: ImagesConfig,
) -> NormalizedImage | ImageFailure:
    try:
        return await asyncio.to_thread(_normalize_image, image, config)
    except _SourceTooLargeError:
        category = ImageFailureCategory.TOO_LARGE
    except (
        UnidentifiedImageError,
        PILImage.DecompressionBombError,
        PILImage.DecompressionBombWarning,
        _InvalidImageError,
    ):
        category = ImageFailureCategory.INVALID
    except OSError, ValueError:
        category = ImageFailureCategory.PROCESSING
    return ImageFailure(
        label=image.collected.label,
        stage=ImageFailureStage.NORMALIZATION,
        category=category,
    )


def _normalize_image(image: _AcquiredImage, config: ImagesConfig) -> NormalizedImage:
    with warnings.catch_warnings():
        warnings.simplefilter("error", PILImage.DecompressionBombWarning)
        with PILImage.open(BytesIO(image.data)) as source:
            source.seek(0)
            width, height = source.size
            if width <= 0 or height <= 0:
                raise _InvalidImageError
            if width * height > config.max_pixels:
                raise _SourceTooLargeError
            source.load()
            transposed = ImageOps.exif_transpose(source)
            if transposed.width * transposed.height > config.max_pixels:
                raise _SourceTooLargeError
            rgb = _composite_rgb(transposed)

    if max(rgb.size) > config.max_edge_px:
        rgb.thumbnail(
            (config.max_edge_px, config.max_edge_px),
            PILImage.Resampling.LANCZOS,
        )
    jpeg_bytes, width, height = _encode_bounded_jpeg(rgb, config)
    return NormalizedImage(
        label=image.collected.label,
        jpeg_bytes=jpeg_bytes,
        source_bytes=len(image.data),
        width=width,
        height=height,
        sha256=image.sha256,
    )


def _composite_rgb(image: PILImage.Image) -> PILImage.Image:
    has_alpha = image.mode in {"RGBA", "LA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    if not has_alpha:
        return image.convert("RGB")
    rgba = image.convert("RGBA")
    background = PILImage.new("RGB", rgba.size, "white")
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background


def _encode_bounded_jpeg(
    image: PILImage.Image,
    config: ImagesConfig,
) -> tuple[bytes, int, int]:
    qualities = tuple(
        dict.fromkeys(
            quality
            for quality in (
                config.jpeg_quality,
                80,
                70,
                60,
                50,
                40,
                30,
            )
            if quality <= config.jpeg_quality
        )
    )
    current = image
    smallest = b""
    for resize_round in range(8):
        for quality in qualities:
            output = BytesIO()
            current.save(
                output,
                format="JPEG",
                quality=quality,
                optimize=True,
            )
            payload = output.getvalue()
            if not smallest or len(payload) < len(smallest):
                smallest = payload
            if _model_payload_size(len(payload)) <= config.max_payload_bytes:
                return payload, current.width, current.height
        if resize_round == 7 or min(current.size) <= 1:
            break
        binary_budget = max(
            0,
            (config.max_payload_bytes - len(_DATA_URL_PREFIX)) // 4 * 3,
        )
        ratio = (
            math.sqrt(binary_budget / len(smallest)) * 0.95 if binary_budget else 0.5
        )
        ratio = min(0.85, max(0.5, ratio))
        new_size = (
            max(1, int(current.width * ratio)),
            max(1, int(current.height * ratio)),
        )
        if new_size == current.size:
            break
        current = current.resize(new_size, PILImage.Resampling.LANCZOS)
        smallest = b""
    raise _SourceTooLargeError


def _model_payload_size(jpeg_size: int) -> int:
    return len(_DATA_URL_PREFIX) + 4 * ((jpeg_size + 2) // 3)


def _to_prepared_image(image: NormalizedImage) -> PreparedImage:
    encoded = base64.b64encode(image.jpeg_bytes).decode("ascii")
    data_url = f"{_DATA_URL_PREFIX}{encoded}"
    return PreparedImage(
        label=image.label,
        part=ImagePart(url=data_url, detail="auto"),
        payload_bytes=len(data_url.encode("utf-8")),
        width=image.width,
        height=image.height,
        sha256=image.sha256,
    )


__all__ = [
    "AdapterImageFetcher",
    "EmptyInputError",
    "ImageLimitError",
    "ImagePreparationResult",
    "ImageURLResolver",
    "InputCollectionError",
    "UnsupportedInputError",
    "collect_input",
    "prepare_images",
]
