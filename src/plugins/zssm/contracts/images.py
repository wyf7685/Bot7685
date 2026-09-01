from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from ._validation import _http_url, _image_label, _sha256

if TYPE_CHECKING:
    from src.service.llm import ImagePart


@dataclass(frozen=True, slots=True)
class PreparedImage:
    label: str
    part: ImagePart = field(repr=False)
    payload_bytes: int
    width: int
    height: int
    sha256: str
    qr_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        object.__setattr__(self, "sha256", _sha256(self.sha256))
        qr_urls = tuple(_http_url(url, "QR URL") for url in self.qr_urls)
        if len(set(qr_urls)) != len(qr_urls):
            raise ValueError("QR URLs must be unique")
        object.__setattr__(self, "qr_urls", qr_urls)
        if self.payload_bytes <= 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("prepared image sizes must be positive")


class ImageFailureStage(StrEnum):
    ACQUISITION = "acquisition"
    NORMALIZATION = "normalization"
    VISION = "vision"


class ImageFailureCategory(StrEnum):
    UNAVAILABLE = "unavailable"
    TOO_LARGE = "too_large"
    INVALID = "invalid"
    DOWNLOAD = "download"
    PROCESSING = "processing"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class ImageFailure:
    label: str
    stage: ImageFailureStage
    category: ImageFailureCategory

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))


@dataclass(frozen=True, slots=True)
class ImageStageStatistics:
    requested: int = 0
    unique: int = 0
    prepared: int = 0
    acquisition_failed: int = 0
    normalization_failed: int = 0
    vision_succeeded: int = 0
    vision_failed: int = 0
    vision_truncated: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__slots__)
        if any(value < 0 for value in values):
            raise ValueError("image statistics must not be negative")
        if self.unique > self.requested:
            raise ValueError("unique images must not exceed requested images")
        if self.prepared + self.preparation_failed != self.unique:
            raise ValueError("every unique image must be prepared or fail preparation")
        if self.vision_succeeded + self.vision_failed > self.prepared:
            raise ValueError("vision outcomes must not exceed prepared images")
        if self.vision_truncated > self.vision_succeeded:
            raise ValueError("truncated observations must have succeeded")

    @property
    def preparation_failed(self) -> int:
        return self.acquisition_failed + self.normalization_failed

    @property
    def partial_success(self) -> bool:
        vision_attempted = self.vision_succeeded + self.vision_failed > 0
        usable_successes = self.vision_succeeded if vision_attempted else self.prepared
        failures = self.preparation_failed + self.vision_failed
        return usable_successes > 0 and failures > 0


__all__ = [
    "ImageFailure",
    "ImageFailureCategory",
    "ImageFailureStage",
    "ImageStageStatistics",
    "PreparedImage",
]
