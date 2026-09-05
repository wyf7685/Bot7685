"""Internal completion contracts shared by runtimes and protocol adapters."""

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from .config import AnthropicThinkingConfig, EndpointProtocol
from .exceptions import LLMErrorCategory
from .models import (
    ChatInput,
    ChatInputPart,
    ImagePart,
    ModelCallTrace,
    ModelCapabilities,
    ReasoningEffort,
    StructuredOutputMode,
    TextPart,
)
from .tools import ToolDefinition
from .usage import TokenUsage

_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class CompletionStop(StrEnum):
    COMPLETE = "complete"
    TOOL_CALLS = "tool_calls"
    LENGTH = "length"
    REFUSAL = "refusal"
    FAILED = "failed"


class ReplayPayload(Protocol):
    """Adapter-owned, in-memory replay data bound to one endpoint and model."""

    @property
    def protocol(self) -> EndpointProtocol: ...

    @property
    def owner(self) -> object: ...

    @property
    def model_id(self) -> str: ...


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str

    def __post_init__(self) -> None:
        call_id = self.id.strip()
        name = self.name.strip()
        if not call_id or len(call_id) > 256:
            raise ValueError("tool call id must contain 1-256 characters")
        if any(ord(character) < 32 or ord(character) == 127 for character in call_id):
            raise ValueError("tool call id must be printable")
        if not _TOOL_NAME_PATTERN.fullmatch(name):
            raise ValueError("tool call name is invalid")
        if not isinstance(self.arguments, str):
            raise TypeError("tool call arguments must be JSON text")
        object.__setattr__(self, "id", call_id)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    name: str
    content: str
    is_error: bool

    def __post_init__(self) -> None:
        if not self.call_id:
            raise ValueError("tool result call_id must not be empty")
        if not _TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("tool result name is invalid")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("tool result content must not be empty")
        if not isinstance(self.is_error, bool):
            raise TypeError("tool result is_error must be a boolean")


@dataclass(frozen=True, slots=True)
class UserTurn:
    parts: tuple[ChatInputPart, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", tuple(self.parts))
        if not self.parts:
            raise ValueError("user turn must contain at least one part")
        if any(not isinstance(part, (TextPart, ImagePart)) for part in self.parts):
            raise TypeError("user turn contains an unsupported part")


@dataclass(frozen=True, slots=True)
class CompletionReply:
    content: str | None
    tool_calls: tuple[ToolCall, ...]
    usage: TokenUsage
    stop: CompletionStop
    finish_reason: str | None = None
    replay: ReplayPayload | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        if self.content is not None and not isinstance(self.content, str):
            raise TypeError("completion content must be text or null")
        if any(not isinstance(call, ToolCall) for call in self.tool_calls):
            raise TypeError("completion contains an invalid tool call")
        ids = tuple(call.id for call in self.tool_calls)
        if len(ids) != len(set(ids)):
            raise ValueError("tool call ids must be unique within a model turn")
        if not isinstance(self.usage, TokenUsage):
            raise TypeError("completion usage must be TokenUsage")
        if not isinstance(self.stop, CompletionStop):
            raise TypeError("completion stop must be CompletionStop")
        if bool(self.tool_calls) != (self.stop is CompletionStop.TOOL_CALLS):
            raise ValueError("only a complete tool-call turn can contain tool calls")
        if self.finish_reason is not None and not isinstance(self.finish_reason, str):
            raise TypeError("completion finish reason must be text or null")


@dataclass(frozen=True, slots=True)
class ModelTurn:
    reply: CompletionReply
    trace: ModelCallTrace


type HistoryItem = ModelTurn | ToolResult | UserTurn


@dataclass(frozen=True, slots=True)
class StructuredOutputRequest:
    schema: dict[str, Any]
    mode: StructuredOutputMode


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    prompt: ChatInput
    system_prompt: str | None = None
    history: tuple[HistoryItem, ...] = ()
    tools: tuple[ToolDefinition, ...] = ()
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: ReasoningEffort | None = None
    parallel_tool_calls: bool = False
    structured: StructuredOutputRequest | None = None
    thinking: AnthropicThinkingConfig | None = None

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
            or self.max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be a positive integer")
        if self.temperature is not None and (
            isinstance(self.temperature, bool)
            or not math.isfinite(self.temperature)
            or self.temperature < 0
        ):
            raise ValueError("temperature must be finite and nonnegative")
        if self.structured is not None and self.tools:
            raise ValueError("structured output and tool execution are separate modes")


class EndpointBackend(Protocol):
    async def complete(
        self, model_id: str, request: CompletionRequest
    ) -> CompletionReply: ...

    async def aclose(self) -> None: ...


class ModelBackend(Protocol):
    @property
    def alias(self) -> str: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def complete(self, request: CompletionRequest) -> ModelTurn: ...


class BackendError(Exception):
    """An SDK failure classified without exposing provider messages or payloads."""

    def __init__(
        self, category: LLMErrorCategory, *, cause: BaseException | None = None
    ) -> None:
        self.category = category
        self.cause = cause
        super().__init__(f"LLM backend error: {category.value}")


class InvalidResponseError(BackendError):
    def __init__(self, message: str = "invalid provider response") -> None:
        super().__init__(LLMErrorCategory.INVALID_RESPONSE)
        self.detail = message


class UnsupportedStructuredMode(BackendError):
    def __init__(
        self,
        mode: StructuredOutputMode,
        *,
        usage: TokenUsage | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(LLMErrorCategory.STRUCTURED_OUTPUT, cause=cause)
        self.mode = mode
        self.usage = usage if usage is not None else TokenUsage()


def field_value(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def token_count(value: Any, name: str) -> int:
    count = field_value(value, name)
    if count is None:
        return 0
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise InvalidResponseError("invalid token usage")
    return count


def require_replay[T: ReplayPayload](
    turn: ModelTurn,
    replay_type: type[T],
    *,
    owner: object,
    model_id: str,
) -> T:
    replay = turn.reply.replay
    if (
        not isinstance(replay, replay_type)
        or replay.owner is not owner
        or replay.model_id != model_id
    ):
        raise InvalidResponseError("history belongs to a different endpoint or model")
    return replay
