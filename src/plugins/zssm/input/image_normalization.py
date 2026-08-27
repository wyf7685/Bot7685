import asyncio
import base64
import math
import warnings
from io import BytesIO
from typing import Final

from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from src.service.llm import ImagePart

from ..config import ImagesConfig
from ..contracts import (
    ImageFailure,
    ImageFailureCategory,
    ImageFailureStage,
    NormalizedImage,
    PreparedImage,
)
from .image_acquisition import (
    _AcquiredImage,
    _InvalidImageError,
    _SourceTooLargeError,
)

_DATA_URL_PREFIX: Final = "data:image/jpeg;base64,"


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
