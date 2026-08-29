from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Protocol

from pydantic import StringConstraints

from ._validation import (
    _MESSAGE_IMAGE_ID_PATTERN,
    _image_label,
    _message_image_id,
    _participant_alias,
)

if TYPE_CHECKING:
    from nonebot_plugin_alconna import Image, UniMessage

    from src.service.llm import ChatInputPart


MessageImageId = Annotated[
    str, StringConstraints(pattern=rf"^{_MESSAGE_IMAGE_ID_PATTERN}$")
]


class InputLocation(StrEnum):
    QUOTED = "quoted"
    CURRENT = "current"


@dataclass(frozen=True, slots=True)
class CollectedImageInput:
    label: str
    location: InputLocation
    source_index: int
    segment: Image = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        if self.source_index < 0:
            raise ValueError("source_index must not be negative")


@dataclass(frozen=True, slots=True)
class DeferredImageInput:
    image_id: str
    location: InputLocation
    source_index: int
    segment: Image = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "image_id", _message_image_id(self.image_id))
        if self.source_index < 0:
            raise ValueError("source_index must not be negative")
        if not self.segment.sticker:
            raise ValueError("deferred input images must be stickers")


@dataclass(frozen=True, slots=True)
class MessageImageRef:
    image_id: str
    sticker: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "image_id", _message_image_id(self.image_id))


class MessageImageRegistry(Protocol):
    def register(self, segment: Image) -> MessageImageRef: ...
    def get(self, image_id: str) -> Image | None: ...


@dataclass(frozen=True, slots=True)
class CollectedInput:
    """A copied run snapshot; aliases alone never make an invocation nonempty."""

    prompt_text: str
    prompt_parts: tuple[ChatInputPart, ...]
    current: UniMessage = field(repr=False, compare=False)
    quoted: UniMessage | None = field(default=None, repr=False, compare=False)
    images: tuple[CollectedImageInput, ...] = ()
    deferred_images: tuple[DeferredImageInput, ...] = ()
    omitted_images: int = 0
    participant_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_parts", tuple(self.prompt_parts))
        object.__setattr__(self, "images", tuple(self.images))
        object.__setattr__(self, "deferred_images", tuple(self.deferred_images))
        if self.omitted_images < 0:
            raise ValueError("omitted image count must not be negative")
        object.__setattr__(self, "participant_aliases", tuple(self.participant_aliases))
        object.__setattr__(self, "current", self.current.copy())
        if self.quoted is not None:
            object.__setattr__(self, "quoted", self.quoted.copy())
        indices = tuple(image.source_index for image in self.images)
        if indices != tuple(sorted(indices)):
            raise ValueError("images must retain source order")
        labels = tuple(image.label for image in self.images)
        if labels != tuple(f"image-{i}" for i in range(1, len(labels) + 1)):
            raise ValueError("images must use contiguous stable labels")
        deferred_indices = tuple(image.source_index for image in self.deferred_images)
        if deferred_indices != tuple(sorted(deferred_indices)):
            raise ValueError("deferred images must retain source order")
        deferred_ids = tuple(image.image_id for image in self.deferred_images)
        if deferred_ids != tuple(f"i{i}" for i in range(1, len(deferred_ids) + 1)):
            raise ValueError("deferred images must use contiguous stable IDs")
        for alias in self.participant_aliases:
            _participant_alias(alias)
        if len(set(self.participant_aliases)) != len(self.participant_aliases):
            raise ValueError("participant_aliases must be unique")
        if self.is_empty:
            raise ValueError(
                "collected input must contain text, prompt parts, or images"
            )

    @property
    def is_empty(self) -> bool:
        return (
            not self.prompt_text.strip()
            and not self.prompt_parts
            and not self.images
            and not self.deferred_images
        )


__all__ = [
    "CollectedImageInput",
    "CollectedInput",
    "DeferredImageInput",
    "InputLocation",
    "MessageImageId",
    "MessageImageRef",
    "MessageImageRegistry",
]
