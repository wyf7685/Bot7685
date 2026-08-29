from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from ._validation import _citation_id, _http_url, _nonempty
from .run import RunStatistics, ToolDisplayEntry
from .web import Citation

if TYPE_CHECKING:
    from nonebot_plugin_alconna import UniMessage


@dataclass(frozen=True, slots=True)
class SourceEntry:
    citation_id: str
    title: str
    url: str
    source: str | None = None
    published: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        for name in ("source", "published"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))

    @classmethod
    def from_citation(cls, citation: Citation) -> SourceEntry:
        return cls(
            citation.citation_id,
            citation.title,
            citation.url,
            citation.source,
            citation.published,
        )


class RenderFailureCategory(StrEnum):
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    EMPTY_INPUT = "empty_input"
    UNSUPPORTED_INPUT = "unsupported_input"
    FORWARD = "forward"
    IMAGE = "image"
    LIMITS = "limits"
    PROVIDER = "provider"
    TOOL = "tool"
    RENDER = "render"


@dataclass(frozen=True, slots=True)
class RenderFailure:
    category: RenderFailureCategory
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _nonempty(self.message, "failure message"))


@dataclass(frozen=True, slots=True)
class RenderModel:
    answer: str | None
    current: UniMessage = field(repr=False, compare=False)
    quoted: UniMessage | None = field(default=None, repr=False, compare=False)
    sources: tuple[SourceEntry, ...] = ()
    trace: tuple[ToolDisplayEntry, ...] = ()
    stats: RunStatistics | None = None
    failure: RenderFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "current", self.current.copy())
        if self.quoted is not None:
            object.__setattr__(self, "quoted", self.quoted.copy())
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "trace", tuple(self.trace))
        if (self.answer is None) == (self.failure is None):
            raise ValueError("render model requires exactly one of answer or failure")
        if self.answer is not None:
            object.__setattr__(self, "answer", _nonempty(self.answer, "answer"))
            if self.stats is None:
                raise ValueError("successful render model requires statistics")
        ids = tuple(source.citation_id for source in self.sources)
        if len(set(ids)) != len(ids):
            raise ValueError("render sources must not repeat citation IDs")
        if self.stats is not None and self.stats.tool_calls != len(self.trace):
            raise ValueError("tool trace length must match statistics.tool_calls")


__all__ = [
    "RenderFailure",
    "RenderFailureCategory",
    "RenderModel",
    "SourceEntry",
]
