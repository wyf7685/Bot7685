from dataclasses import dataclass

import httpx

from ..config import ImagesConfig
from ..contracts import (
    CollectedInput,
    ImageFailure,
    ImageStageStatistics,
    PreparedImage,
)
from .image_acquisition import (
    AdapterImageFetcher,
    ImageURLResolver,
    _acquire_all,
    _AcquiredImage,
    _deduplicate_source_references,
    _resolve_global_addresses,
    _SafeImageFetcher,
    _uses_url_source,
)
from .image_normalization import _normalize_all, _to_prepared_image


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
        if len(self.failures) != self.statistics.preparation_failed:
            raise ValueError(
                "image preparation failure count does not match statistics"
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

    candidates = _deduplicate_source_references(collected.images)[: config.max_count]
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
    acquisition_failed = 0
    seen_content: set[str] = set()
    unique_count = 0
    for _candidate, outcome in zip(candidates, acquired_outcomes, strict=True):
        if isinstance(outcome, ImageFailure):
            unique_count += 1
            failures.append(outcome)
            acquisition_failed += 1
            continue
        if outcome.sha256 in seen_content:
            continue
        seen_content.add(outcome.sha256)
        unique_count += 1
        unique_acquired.append(outcome)

    normalized_outcomes = await _normalize_all(unique_acquired, config)
    prepared: list[PreparedImage] = []
    normalization_failed = 0
    for outcome in normalized_outcomes:
        if isinstance(outcome, ImageFailure):
            failures.append(outcome)
            normalization_failed += 1
        else:
            prepared.append(_to_prepared_image(outcome))

    statistics = ImageStageStatistics(
        requested=requested,
        unique=unique_count,
        prepared=len(prepared),
        acquisition_failed=acquisition_failed,
        normalization_failed=normalization_failed,
    )
    return ImagePreparationResult(
        images=tuple(prepared),
        failures=tuple(failures),
        statistics=statistics,
    )


__all__ = ["ImagePreparationResult", "prepare_images"]
