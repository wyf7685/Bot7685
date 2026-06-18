import contextlib
import dataclasses
from typing import TypedDict

with contextlib.suppress(ImportError):
    from nonebot.adapters.milky.message import TYPE_MAPPING, MessageSegment

    class MarkdownData(TypedDict, total=False):
        content: str

    @dataclasses.dataclass
    class Markdown(MessageSegment, element_type="markdown"):
        data: MarkdownData = dataclasses.field(default_factory=dict)

    TYPE_MAPPING.update({Markdown.__element_type__: Markdown})  # ty:ignore[no-matching-overload]
