import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from .exceptions import LLMCapabilityError, LLMErrorCategory, LLMRunError
from .models import (
    AgentLimits,
    AgentRunResult,
    AgentTrace,
    ChatInput,
    ModelCallTrace,
    ToolCallTrace,
    ToolErrorCategory,
)
from .tools import (
    BoundTool,
    ToolArgumentsError,
    ToolDefinition,
    ToolOutputSerializationError,
    ToolOutputTooLargeError,
    serialize_tool_output,
)
from .usage import TokenUsage

_TOOL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_CALL_ID_CHARS = 256
_DEFAULT_AGENT_LIMITS = AgentLimits()


@dataclass(frozen=True, slots=True)
class AgentToolCall:
    """One neutral assistant-requested function call."""

    id: str
    name: str
    arguments: str

    def __post_init__(self) -> None:
        call_id = self.id.strip()
        name = self.name.strip()
        if not call_id:
            raise ValueError("tool call id must not be empty")
        if len(call_id) > _MAX_CALL_ID_CHARS:
            raise ValueError("tool call id is too long")
        if any(ord(character) < 32 or ord(character) == 127 for character in call_id):
            raise ValueError("tool call id must be printable")
        if not _TOOL_NAME_PATTERN.fullmatch(name):
            raise ValueError("tool call name is invalid")
        if not isinstance(self.arguments, str):
            raise TypeError("tool call arguments must be JSON text")
        object.__setattr__(self, "id", call_id)
        object.__setattr__(self, "name", name)


@dataclass(frozen=True, slots=True)
class AgentModelTurn:
    """A provider-neutral assistant turn plus its model statistics."""

    content: str | None
    tool_calls: tuple[AgentToolCall, ...]
    model_alias: str
    model_id: str
    usage: TokenUsage
    elapsed: float
    finish_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        if self.content is not None and not isinstance(self.content, str):
            raise TypeError("assistant content must be text or null")
        if any(not isinstance(call, AgentToolCall) for call in self.tool_calls):
            raise TypeError("tool_calls contains an unsupported value")
        call_ids = tuple(call.id for call in self.tool_calls)
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("tool call ids must be unique within a model turn")
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
class AgentToolResult:
    """One role=tool history item paired to an assistant tool call."""

    call_id: str
    name: str
    content: str

    def __post_init__(self) -> None:
        if not self.call_id:
            raise ValueError("tool result call_id must not be empty")
        if not _TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError("tool result name is invalid")
        if not isinstance(self.content, str) or not self.content:
            raise ValueError("tool result content must not be empty")


type AgentHistoryItem = AgentModelTurn | AgentToolResult


@dataclass(frozen=True, slots=True)
class AgentModelCapabilities:
    """Resolved model identity and tool-call capabilities needed by the loop."""

    model_alias: str
    tools: bool
    parallel_tool_calls: bool

    def __post_init__(self) -> None:
        model_alias = self.model_alias.strip()
        if not model_alias:
            raise ValueError("model_alias must not be empty")
        if self.parallel_tool_calls and not self.tools:
            raise ValueError("parallel_tool_calls requires tools capability")
        object.__setattr__(self, "model_alias", model_alias)


class AgentCompletionBackend(Protocol):
    """Minimal adapter contract required by the provider-neutral agent loop."""

    def resolve_model(
        self,
        model: str | None,
        /,
    ) -> AgentModelCapabilities: ...

    async def complete_turn(
        self,
        *,
        prompt: ChatInput,
        system_prompt: str | None,
        history: tuple[AgentHistoryItem, ...],
        tools: tuple[ToolDefinition, ...],
        model: str,
        temperature: float | None,
        max_output_tokens: int,
        parallel_tool_calls: bool,
    ) -> AgentModelTurn: ...


@dataclass(frozen=True, slots=True)
class _DispatchedToolCall:
    result: AgentToolResult
    trace: ToolCallTrace


async def run_agent(
    backend: AgentCompletionBackend,
    prompt: ChatInput,
    *,
    tools: Sequence[BoundTool[Any, Any]] = (),
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float | None = None,
    limits: AgentLimits = _DEFAULT_AGENT_LIMITS,
) -> AgentRunResult:
    """Run a bounded assistant/tool conversation against a neutral backend."""

    started = perf_counter()
    bound_tools = tuple(tools)
    _validate_bound_tools(bound_tools)
    capabilities = backend.resolve_model(model)
    if bound_tools and not capabilities.tools:
        raise LLMCapabilityError(model_alias=capabilities.model_alias)

    definitions = tuple(tool.definition for tool in bound_tools)
    registry = {tool.name: tool for tool in bound_tools}
    try:
        async with asyncio.timeout(limits.total_timeout_seconds):
            return await _run_bounded_conversation(
                backend=backend,
                prompt=prompt,
                system_prompt=system_prompt,
                definitions=definitions,
                registry=registry,
                capabilities=capabilities,
                temperature=temperature,
                limits=limits,
                started=started,
            )
    except TimeoutError as error:
        raise LLMRunError(
            category=LLMErrorCategory.TIMEOUT,
            model_alias=capabilities.model_alias,
        ) from error


async def _run_bounded_conversation(
    *,
    backend: AgentCompletionBackend,
    prompt: ChatInput,
    system_prompt: str | None,
    definitions: tuple[ToolDefinition, ...],
    registry: dict[str, BoundTool[Any, Any]],
    capabilities: AgentModelCapabilities,
    temperature: float | None,
    limits: AgentLimits,
    started: float,
) -> AgentRunResult:
    history: list[AgentHistoryItem] = []
    model_traces: list[ModelCallTrace] = []
    tool_traces: list[ToolCallTrace] = []
    usage = TokenUsage()
    tool_call_count = 0

    while True:
        if len(model_traces) >= limits.max_model_calls:
            raise LLMRunError(
                category=LLMErrorCategory.LIMITS,
                model_alias=capabilities.model_alias,
            )

        turn = await backend.complete_turn(
            prompt=prompt,
            system_prompt=system_prompt,
            history=tuple(history),
            tools=definitions,
            model=capabilities.model_alias,
            temperature=temperature,
            max_output_tokens=limits.max_output_tokens,
            parallel_tool_calls=capabilities.parallel_tool_calls,
        )

        if not isinstance(turn, AgentModelTurn):
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE,
                model_alias=capabilities.model_alias,
            )
        if turn.model_alias != capabilities.model_alias:
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE,
                model_alias=capabilities.model_alias,
            )

        model_traces.append(
            ModelCallTrace(
                model_alias=turn.model_alias,
                model_id=turn.model_id,
                usage=turn.usage,
                elapsed=turn.elapsed,
                finish_reason=turn.finish_reason,
            )
        )
        usage = usage + turn.usage
        history.append(turn)

        if not turn.tool_calls:
            if turn.content is None or not turn.content.strip():
                raise LLMRunError(
                    category=LLMErrorCategory.INVALID_RESPONSE,
                    model_alias=capabilities.model_alias,
                )
            return AgentRunResult(
                output=turn.content,
                model_alias=turn.model_alias,
                model_id=turn.model_id,
                usage=usage,
                elapsed=perf_counter() - started,
                trace=AgentTrace(
                    model_calls=tuple(model_traces),
                    tool_calls=tuple(tool_traces),
                ),
            )

        if not capabilities.parallel_tool_calls and len(turn.tool_calls) > 1:
            raise LLMCapabilityError(model_alias=capabilities.model_alias)
        if tool_call_count + len(turn.tool_calls) > limits.max_tool_calls:
            raise LLMRunError(
                category=LLMErrorCategory.LIMITS,
                model_alias=capabilities.model_alias,
            )

        dispatched = await _dispatch_tool_round(
            turn.tool_calls,
            registry=registry,
            max_parallel_tools=limits.max_parallel_tools,
            max_result_bytes=limits.max_tool_result_bytes,
        )
        tool_call_count += len(dispatched)
        for item in dispatched:
            history.append(item.result)
            tool_traces.append(item.trace)


async def _dispatch_tool_round(
    calls: tuple[AgentToolCall, ...],
    *,
    registry: dict[str, BoundTool[Any, Any]],
    max_parallel_tools: int,
    max_result_bytes: int,
) -> tuple[_DispatchedToolCall, ...]:
    semaphore = asyncio.Semaphore(max_parallel_tools)

    async def dispatch(call: AgentToolCall) -> _DispatchedToolCall:
        async with semaphore:
            return await _dispatch_tool_call(
                call,
                registry=registry,
                max_result_bytes=max_result_bytes,
            )

    async with asyncio.TaskGroup() as task_group:
        tasks = [task_group.create_task(dispatch(call)) for call in calls]
    return tuple(task.result() for task in tasks)


async def _dispatch_tool_call(
    call: AgentToolCall,
    *,
    registry: dict[str, BoundTool[Any, Any]],
    max_result_bytes: int,
) -> _DispatchedToolCall:
    started = perf_counter()
    tool = registry.get(call.name)
    if tool is None:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.UNKNOWN_TOOL,
            summary="unknown tool",
            elapsed=perf_counter() - started,
        )

    try:
        arguments = tool.validate_arguments(call.arguments)
    except ToolArgumentsError:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.INVALID_ARGUMENTS,
            summary="invalid arguments",
            elapsed=perf_counter() - started,
        )

    try:
        output = await tool.invoke(arguments)
    except Exception:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.EXECUTION,
            summary="handler failed",
            elapsed=perf_counter() - started,
        )

    try:
        content, result_bytes = serialize_tool_output(
            output,
            max_bytes=max_result_bytes,
        )
    except ToolOutputTooLargeError as error:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.RESULT_TOO_LARGE,
            summary="result too large",
            elapsed=perf_counter() - started,
            result_bytes=error.result_bytes,
        )
    except ToolOutputSerializationError:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.EXECUTION,
            summary="invalid result",
            elapsed=perf_counter() - started,
        )

    return _DispatchedToolCall(
        result=AgentToolResult(
            call_id=call.id,
            name=call.name,
            content=content,
        ),
        trace=ToolCallTrace(
            name=call.name,
            summary=output.summary,
            success=True,
            elapsed=perf_counter() - started,
            result_bytes=result_bytes,
        ),
    )


def _failed_tool_call(
    call: AgentToolCall,
    *,
    category: ToolErrorCategory,
    summary: str,
    elapsed: float,
    result_bytes: int = 0,
) -> _DispatchedToolCall:
    content = json.dumps(
        {"error": category.value},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return _DispatchedToolCall(
        result=AgentToolResult(
            call_id=call.id,
            name=call.name,
            content=content,
        ),
        trace=ToolCallTrace(
            name=call.name,
            summary=summary,
            success=False,
            elapsed=elapsed,
            result_bytes=result_bytes,
            error_category=category,
        ),
    )


def _validate_bound_tools(tools: tuple[BoundTool[Any, Any], ...]) -> None:
    if any(not isinstance(tool, BoundTool) for tool in tools):
        raise TypeError("tools contains an unsupported value")
    names = tuple(tool.name for tool in tools)
    if len(names) != len(set(names)):
        raise ValueError("tool names must be unique")
