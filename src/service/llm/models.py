from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from .usage import TokenUsage

type StructuredOutputMode = Literal["json_schema", "json_object"] | None
type ReasoningEffort = Literal[
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
]
_REASONING_EFFORT_ORDER: tuple[ReasoningEffort, ...] = (
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

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


class ModelCapability(StrEnum):
    TOOLS = "tools"
    VISION = "vision"
    STRUCTURED_OUTPUT = "structured_output"
    PARALLEL_TOOL_CALLS = "parallel_tool_calls"
    REASONING_EFFORT = "reasoning_effort"
    TEMPERATURE = "temperature"


class ModelCapabilities(BaseModel):
    """Validated, immutable capabilities shared by config and runtime models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: bool
    vision: bool
    temperature: bool
    reasoning_efforts: tuple[ReasoningEffort, ...] = ()
    structured_output_modes: tuple[StructuredOutputMode, ...]
    parallel_tool_calls: bool

    @field_validator("structured_output_modes")
    @classmethod
    def validate_modes(
        cls, value: tuple[StructuredOutputMode, ...]
    ) -> tuple[StructuredOutputMode, ...]:
        validate_structured_output_modes(value)
        return value

    @field_validator("reasoning_efforts")
    @classmethod
    def validate_reasoning_efforts(
        cls, value: tuple[ReasoningEffort, ...]
    ) -> tuple[ReasoningEffort, ...]:
        if len(set(value)) != len(value):
            raise ValueError("reasoning_efforts must not contain duplicates")
        positions = tuple(_REASONING_EFFORT_ORDER.index(effort) for effort in value)
        if positions != tuple(sorted(positions)):
            raise ValueError("reasoning_efforts must follow none-to-max order")
        return value

    @model_validator(mode="after")
    def validate_tool_capabilities(self) -> Self:
        if self.parallel_tool_calls and not self.tools:
            raise ValueError("parallel_tool_calls requires tools capability")
        return self

    def supports(self, capability: ModelCapability) -> bool:
        if not isinstance(capability, ModelCapability):
            raise TypeError("capability must be ModelCapability")
        match capability:
            case ModelCapability.TOOLS:
                return self.tools
            case ModelCapability.VISION:
                return self.vision
            case ModelCapability.TEMPERATURE:
                return self.temperature
            case ModelCapability.REASONING_EFFORT:
                return bool(self.reasoning_efforts)
            case ModelCapability.STRUCTURED_OUTPUT:
                return bool(self.structured_output_modes)
            case ModelCapability.PARALLEL_TOOL_CALLS:
                return self.parallel_tool_calls

    def resolve_reasoning_effort(
        self, requested: ReasoningEffort | None
    ) -> ReasoningEffort | None:
        if requested is None:
            return None

        requested_index = _REASONING_EFFORT_ORDER.index(requested)
        for candidate in reversed(_REASONING_EFFORT_ORDER[: requested_index + 1]):
            if candidate in self.reasoning_efforts:
                return candidate
        raise ValueError(
            f"model does not support reasoning effort {requested!r} or any lower effort"
        )

    def require(
        self,
        capability: ModelCapability,
        *,
        model_alias: str,
    ) -> None:
        if not self.supports(capability):
            from .exceptions import LLMCapabilityError

            raise LLMCapabilityError(
                model_alias=model_alias,
                capability=capability,
            )


@dataclass(frozen=True, slots=True)
class ModelInfo:
    alias: str
    model_id: str
    capabilities: ModelCapabilities
    selectable: bool

    def __post_init__(self) -> None:
        alias = self.alias.strip()
        model_id = self.model_id.strip()
        if not alias:
            raise ValueError("model alias must not be empty")
        if not model_id:
            raise ValueError("model ID must not be empty")
        if not isinstance(self.capabilities, ModelCapabilities):
            raise TypeError("capabilities must be ModelCapabilities")
        object.__setattr__(self, "alias", alias)
        object.__setattr__(self, "model_id", model_id)

    def require_capability(self, capability: ModelCapability) -> Self:
        self.capabilities.require(capability, model_alias=self.alias)
        return self


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
        url = self.url.strip()
        if not url:
            raise ValueError("image URL must not be empty")
        if self.detail not in {"auto", "low", "high"}:
            raise ValueError("image detail is invalid")
        object.__setattr__(self, "url", url)


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
        model_alias = self.model_alias.strip()
        model_id = self.model_id.strip()
        if not model_alias:
            raise ValueError("model_alias must not be empty")
        if not model_id:
            raise ValueError("model_id must not be empty")
        if not isinstance(self.usage, TokenUsage):
            raise TypeError("usage must be TokenUsage")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")
        object.__setattr__(self, "model_alias", model_alias)
        object.__setattr__(self, "model_id", model_id)


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
    max_tool_images: int = 4
    max_tool_image_bytes: int = 20 * 1024 * 1024
    total_timeout_seconds: float = 120.0
    max_output_tokens: int = 2000

    def __post_init__(self) -> None:
        for name in (
            "max_model_calls",
            "max_tool_calls",
            "max_parallel_tools",
            "max_tool_result_bytes",
            "max_tool_images",
            "max_tool_image_bytes",
            "max_output_tokens",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.total_timeout_seconds <= 0:
            raise ValueError("total_timeout_seconds must be positive")
        if self.max_parallel_tools > self.max_tool_calls:
            raise ValueError("max_parallel_tools must not exceed max_tool_calls")


class ToolErrorCategory(StrEnum):
    UNKNOWN_TOOL = "unknown_tool"
    INVALID_ARGUMENTS = "invalid_arguments"
    EXECUTION = "execution"
    REPORTED = "reported"
    RESULT_TOO_LARGE = "result_too_large"


@dataclass(frozen=True, slots=True)
class ModelCallTrace:
    model_alias: str
    model_id: str
    usage: TokenUsage
    elapsed: float
    finish_reason: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    structured_mode: StructuredOutputMode = None

    def __post_init__(self) -> None:
        model_alias = self.model_alias.strip()
        model_id = self.model_id.strip()
        if not model_alias:
            raise ValueError("model_alias must not be empty")
        if not model_id:
            raise ValueError("model_id must not be empty")
        if not isinstance(self.usage, TokenUsage):
            raise TypeError("usage must be TokenUsage")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")
        object.__setattr__(self, "model_alias", model_alias)
        object.__setattr__(self, "model_id", model_id)


@dataclass(frozen=True, slots=True)
class ToolCallTrace:
    name: str
    summary: str
    success: bool
    elapsed: float
    result_bytes: int
    error_category: ToolErrorCategory | None = None
    image_count: int = 0
    image_bytes: int = 0

    def __post_init__(self) -> None:
        name = self.name.strip()
        summary = self.summary.strip()
        if not name:
            raise ValueError("tool name must not be empty")
        if not summary:
            raise ValueError("tool summary must not be empty")
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")
        if self.result_bytes < 0:
            raise ValueError("result_bytes must not be negative")
        if self.image_count < 0 or self.image_bytes < 0:
            raise ValueError("tool image trace values must not be negative")
        if self.success == (self.error_category is not None):
            raise ValueError(
                "failed tool calls require exactly one safe error category"
            )
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "summary", summary)


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
        if not isinstance(self.trace, AgentTrace):
            raise TypeError("trace must be AgentTrace")
        if not self.output.strip():
            raise ValueError("agent output must not be empty")

    @property
    def model_call_count(self) -> int:
        return self.trace.model_call_count

    @property
    def tool_call_count(self) -> int:
        return self.trace.tool_call_count
