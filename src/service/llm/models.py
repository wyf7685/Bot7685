from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from .usage import TokenUsage

type StructuredOutputMode = Literal["json_schema", "json_object"] | None
_STRUCTURED_OUTPUT_MODE_ORDER: tuple[StructuredOutputMode, ...] = (
    "json_schema",
    "json_object",
    None,
)


def validate_structured_output_modes(
    modes: tuple[StructuredOutputMode, ...],
) -> None:
    """Validate an ordered structured-output fallback sequence, if supported."""
    if len(set(modes)) != len(modes):
        raise ValueError("structured_output_modes must not contain duplicates")

    positions = tuple(_STRUCTURED_OUTPUT_MODE_ORDER.index(mode) for mode in modes)
    if positions != tuple(sorted(positions)):
        raise ValueError(
            "structured_output_modes must follow json_schema, json_object, null order"
        )


@dataclass(frozen=True, slots=True)
class TextPart:
    text: str

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("text must not be empty")


@dataclass(frozen=True, slots=True)
class ImagePart:
    url: str
    detail: Literal["auto", "low", "high"] = "auto"

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ValueError("image URL must not be empty")


type ChatInputPart = TextPart | ImagePart


@dataclass(frozen=True, slots=True)
class ChatInput:
    parts: tuple[ChatInputPart, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(self.parts))
        if not self.parts:
            raise ValueError("chat input must contain at least one part")
        if any(not isinstance(part, (TextPart, ImagePart)) for part in self.parts):
            raise TypeError("chat input contains an unsupported part")

    @classmethod
    def from_text(cls, text: str) -> ChatInput:
        return cls(parts=(TextPart(text=text),))

    @property
    def has_images(self) -> bool:
        return any(isinstance(part, ImagePart) for part in self.parts)


@dataclass(frozen=True, slots=True)
class RunResult[T]:
    output: T
    model_alias: str
    model_id: str
    usage: TokenUsage
    elapsed: float

    def __post_init__(self) -> None:
        if not self.model_alias.strip():
            raise ValueError("model_alias must not be empty")
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")


class StructuredOutputFallbackReason(StrEnum):
    RESPONSE_FORMAT_UNSUPPORTED = "response_format_unsupported"


@dataclass(frozen=True, slots=True)
class StructuredRunResult[T](RunResult[T]):
    mode_used: StructuredOutputMode
    attempted_modes: tuple[StructuredOutputMode, ...]
    fallback_reasons: tuple[StructuredOutputFallbackReason, ...]

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "attempted_modes", tuple(self.attempted_modes))
        object.__setattr__(self, "fallback_reasons", tuple(self.fallback_reasons))
        if not self.attempted_modes:
            raise ValueError("attempted_modes must not be empty")
        validate_structured_output_modes(self.attempted_modes)
        if self.attempted_modes[-1] != self.mode_used:
            raise ValueError("mode_used must be the final attempted mode")
        if len(self.fallback_reasons) != len(self.attempted_modes) - 1:
            raise ValueError("each failed structured-output attempt needs one reason")


@dataclass(frozen=True, slots=True)
class AgentLimits:
    max_model_calls: int = 8
    max_tool_calls: int = 16
    max_parallel_tools: int = 4
    max_tool_result_bytes: int = 64 * 1024
    total_timeout_seconds: float = 120.0
    max_output_tokens: int = 2000

    def __post_init__(self) -> None:
        for name in (
            "max_model_calls",
            "max_tool_calls",
            "max_parallel_tools",
            "max_tool_result_bytes",
            "max_output_tokens",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")


class ToolErrorCategory(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION = "execution"
    RESULT_TOO_LARGE = "result_too_large"


@dataclass(frozen=True, slots=True)
class ModelCallTrace:
    model_alias: str
    model_id: str
    usage: TokenUsage
    elapsed: float
    finish_reason: str | None = None
    structured_mode: StructuredOutputMode = None

    def __post_init__(self) -> None:
        if not self.model_alias.strip():
            raise ValueError("model_alias must not be empty")
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")


@dataclass(frozen=True, slots=True)
class ToolCallTrace:
    name: str
    summary: str
    success: bool
    elapsed: float
    result_bytes: int
    error_category: ToolErrorCategory | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not self.summary.strip():
            raise ValueError("tool summary must not be empty")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")
        if self.result_bytes < 0:
            raise ValueError("result_bytes must not be negative")
        if self.success == (self.error_category is not None):
            raise ValueError(
                "failed tool calls require exactly one safe error category"
            )


@dataclass(frozen=True, slots=True)
class AgentTrace:
    model_calls: tuple[ModelCallTrace, ...] = ()
    tool_calls: tuple[ToolCallTrace, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_calls", tuple(self.model_calls))
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))

    @property
    def model_call_count(self) -> int:
        return len(self.model_calls)

    @property
    def tool_call_count(self) -> int:
        return len(self.tool_calls)


@dataclass(frozen=True, slots=True)
class AgentRunResult(RunResult[str]):
    trace: AgentTrace

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.output.strip():
            raise ValueError("agent output must not be empty")

    @property
    def model_call_count(self) -> int:
        return self.trace.model_call_count

    @property
    def tool_call_count(self) -> int:
        return self.trace.tool_call_count
