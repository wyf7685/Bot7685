import re
from collections.abc import Iterable
from typing import Final

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

from src.service.llm import TextPart

from ..config import ImagesConfig
from ..contracts.input import (
    CollectedImageInput,
    CollectedInput,
    DeferredImageInput,
    InputLocation,
)
from ..contracts.participants import ParticipantResolver
from .cards import CardURLResolver, _render_hyper_prompt, _resolve_card_urls
from .image_acquisition import _deduplicate_source_references

_PLACEHOLDER_TYPE_RE: Final = re.compile(r"[^a-z0-9_-]+")
_MEDIA_PLACEHOLDERS: Final[dict[type[Segment], str]] = {
    Audio: "[audio]",
    Voice: "[voice]",
    Video: "[video]",
    File: "[file]",
}


class InputCollectionError(ValueError):
    """A safe, user-correctable input collection failure."""


class EmptyInputError(InputCollectionError):
    """The invocation contains no substantive text or media."""


class UnsupportedInputError(InputCollectionError):
    """The invocation contains a segment that cannot be flattened safely."""


async def collect_input(
    current: UniMessage,
    quoted: UniMessage | None,
    *,
    invoker_raw_id: str,
    participant_resolver: ParticipantResolver,
    config: ImagesConfig,
    card_url_resolver: CardURLResolver | None = None,
) -> CollectedInput:
    """Collect a stable, model-safe snapshot with bounded card-link resolution."""

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
    resolved_card_urls = await _resolve_card_urls(
        ordered_messages,
        card_url_resolver,
    )

    invoker = participant_resolver.observe(invoker_raw_id, is_invoker=True)
    participant_aliases = [invoker.participant_alias]
    seen_aliases = {invoker.participant_alias}
    images: list[CollectedImageInput] = []
    deferred_images: list[DeferredImageInput] = []
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
                if segment.sticker:
                    image_id = f"i{len(deferred_images) + 1}"
                    deferred_images.append(
                        DeferredImageInput(
                            image_id=image_id,
                            location=location,
                            source_index=source_index,
                            segment=segment,
                        )
                    )
                    fragments.append(f"[sticker:{image_id}]")
                else:
                    images.append(
                        CollectedImageInput(
                            label=f"image-{len(images) + 1}",
                            location=location,
                            source_index=source_index,
                            segment=segment,
                        )
                    )
                substantive = True
            elif isinstance(segment, Hyper):
                fragments.append(_render_hyper_prompt(segment, resolved_card_urls))
                substantive = True
            elif isinstance(segment, Reply):
                pass
            else:
                fragments.append(_safe_placeholder(segment))
                substantive = substantive or not isinstance(segment, (At, AtAll))
            source_index += 1
        rendered[location] = "".join(fragments)
    unique_images = _deduplicate_source_references(tuple(images))
    omitted_images = max(0, len(unique_images) - config.max_count)
    images = [
        CollectedImageInput(
            label=f"image-{index}",
            location=image.location,
            source_index=image.source_index,
            segment=image.segment,
        )
        for index, image in enumerate(unique_images[: config.max_count], start=1)
    ]

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
    if omitted_images:
        prompt_parts_list.append(
            TextPart(
                f"Image input notice: only the first {config.max_count} non-sticker "
                f"image(s) were included; {omitted_images} additional non-sticker "
                "image(s) were omitted because the image limit was reached."
            )
        )
    prompt_parts = tuple(prompt_parts_list)
    prompt_text = "\n\n".join(part.text for part in prompt_parts)
    return CollectedInput(
        prompt_text=prompt_text,
        prompt_parts=prompt_parts,
        current=current_snapshot,
        quoted=quoted_snapshot,
        images=tuple(images),
        deferred_images=tuple(deferred_images),
        participant_aliases=tuple(participant_aliases),
        omitted_images=omitted_images,
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
    if isinstance(segment, Keyboard):
        return "[interactive]"
    type_name = _PLACEHOLDER_TYPE_RE.sub("-", segment.type.lower()).strip("-")[:32]
    return f"[{type_name or "segment"}]"


__all__ = [
    "EmptyInputError",
    "InputCollectionError",
    "UnsupportedInputError",
    "collect_input",
]
