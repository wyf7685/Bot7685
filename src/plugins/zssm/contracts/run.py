from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from ._validation import _nonempty, _participant_alias
from .images import ImageStageStatistics

if TYPE_CHECKING:
    from src.service.llm import TokenUsage


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ZssmInvocationFacts:
    started_at: datetime
    active_model: str
    invoker_alias: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        object.__setattr__(
            self, "active_model", _nonempty(self.active_model, "active_model")
        )
        object.__setattr__(
            self, "invoker_alias", _participant_alias(self.invoker_alias)
        )


class ToolDisplayStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolDisplayEntry:
    name: str
    summary: str
    status: ToolDisplayStatus
    elapsed: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "tool name"))
        summary = _nonempty(self.summary, "tool summary")
        if len(summary) > 160 or "\n" in summary or "\r" in summary:
            raise ValueError(
                "tool summary must be a single line of at most 160 characters"
            )
        object.__setattr__(self, "summary", summary)
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")


@dataclass(frozen=True, slots=True)
class ModelStageUsage:
    model_alias: str
    model_id: str
    calls: int
    usage_calls: int
    usage: TokenUsage
    elapsed: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_alias", _nonempty(self.model_alias, "model_alias")
        )
        object.__setattr__(self, "model_id", _nonempty(self.model_id, "model_id"))
        if self.calls < 0 or not 0 <= self.usage_calls <= self.calls:
            raise ValueError("stage call counts are inconsistent")
        if self.elapsed < 0:
            raise ValueError("stage elapsed must not be negative")


@dataclass(frozen=True, slots=True)
class RunStatistics:
    total_elapsed: float
    primary_usage: ModelStageUsage
    vision_usage: ModelStageUsage | None
    images: ImageStageStatistics
    tool_calls: int
    tool_failures: int
    tool_elapsed: float
    tool_images: int = 0
    tool_image_bytes: int = 0

    def __post_init__(self) -> None:
        if self.total_elapsed < 0 or self.tool_elapsed < 0:
            raise ValueError("elapsed values must not be negative")
        if self.tool_calls < 0 or not 0 <= self.tool_failures <= self.tool_calls:
            raise ValueError("tool counts are inconsistent")
        if self.tool_images < 0 or self.tool_image_bytes < 0:
            raise ValueError("tool image statistics must not be negative")


__all__ = [
    "ModelStageUsage",
    "RunStatistics",
    "ToolDisplayEntry",
    "ToolDisplayStatus",
    "ZssmInvocationFacts",
]
