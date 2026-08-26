import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from nonebot import logger
from nonebot.utils import escape_tag

from .exceptions import LLMErrorCategory, LLMRunError, LLMServiceError
from .models import (
    AgentLimits,
    AgentRunResult,
    AgentTrace,
    ChatInput,
    ModelCallTrace,
    ModelCapabilities,
    ModelCapability,
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


def _safe_log_text(value: object, limit: int = 80) -> str:
    compact = re.sub(r"\s+", " ", str(value)).strip()
    return escape_tag(compact[:limit] or "none")


def _cause_name(error: BaseException) -> str:
    if isinstance(error, LLMServiceError) and error.cause is not None:
        return type(error.cause).__name__
    return type(error).__name__


def _log_event(
    correlation_id: str | None,
    level: str,
    component: str,
    message: str,
) -> None:
    if correlation_id is None:
        return
    run = _safe_log_text(correlation_id, 32)
    logger.opt(colors=True).log(
        level,
        f"<m>{component}</m> | run=<c>{run}</> | {message}",
    )


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


class AgentCompletionBackend(Protocol):
    """Minimal adapter contract required by the provider-neutral agent loop."""

    @property
    def model_alias(self) -> str: ...

    @property
    def capabilities(self) -> ModelCapabilities: ...

    async def complete_turn(
        self,
        *,
        prompt: ChatInput,
        system_prompt: str | None,
        history: tuple[AgentHistoryItem, ...],
        tools: tuple[ToolDefinition, ...],
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
    temperature: float | None = None,
    limits: AgentLimits = _DEFAULT_AGENT_LIMITS,
    correlation_id: str | None = None,
) -> AgentRunResult:
    """Run a bounded assistant/tool conversation against a neutral backend."""

    started = perf_counter()
    bound_tools = tuple(tools)
    _validate_bound_tools(bound_tools)
    model_alias = backend.model_alias.strip()
    if not model_alias:
        raise ValueError("backend model alias must not be empty")
    capabilities = backend.capabilities
    if not isinstance(capabilities, ModelCapabilities):
        raise TypeError("backend capabilities must be ModelCapabilities")
    if prompt.has_images:
        capabilities.require(ModelCapability.VISION, model_alias=model_alias)
    if bound_tools:
        capabilities.require(ModelCapability.TOOLS, model_alias=model_alias)
    safe_model_alias = _safe_log_text(model_alias)
    _log_event(
        correlation_id,
        "INFO",
        "LLM::Agent",
        f"<b>started</> | model=<g>{safe_model_alias}</> "
        f"tools=<c>{len(bound_tools)}</> "
        f"limits=<c>models:{limits.max_model_calls} tools:{limits.max_tool_calls} "
        f"parallel:{limits.max_parallel_tools} "
        f"timeout:{limits.total_timeout_seconds:g}s</>",
    )

    definitions = tuple(tool.definition for tool in bound_tools)
    registry = {tool.name: tool for tool in bound_tools}
    try:
        async with asyncio.timeout(limits.total_timeout_seconds):
            result = await _run_bounded_conversation(
                backend=backend,
                prompt=prompt,
                system_prompt=system_prompt,
                definitions=definitions,
                registry=registry,
                model_alias=model_alias,
                capabilities=capabilities,
                temperature=temperature,
                limits=limits,
                started=started,
                correlation_id=correlation_id,
            )
    except asyncio.CancelledError:
        _log_event(
            correlation_id,
            "INFO",
            "LLM::Agent",
            f"<y>cancelled</> | "
            f"elapsed=<c>{(perf_counter() - started) * 1000:.1f}ms</>",
        )
        raise
    except TimeoutError as error:
        _log_event(
            correlation_id,
            "WARNING",
            "LLM::Agent",
            f"<r>failed</> | category=<y>timeout</> cause=<r>TimeoutError</> "
            f"elapsed=<c>{(perf_counter() - started) * 1000:.1f}ms</>",
        )
        raise LLMRunError(
            category=LLMErrorCategory.TIMEOUT,
            model_alias=model_alias,
        ) from error
    except LLMServiceError as error:
        _log_event(
            correlation_id,
            "WARNING",
            "LLM::Agent",
            f"<r>failed</> | category=<y>{error.category.value}</> "
            f"cause=<r>{_safe_log_text(_cause_name(error))}</> "
            f"elapsed=<c>{(perf_counter() - started) * 1000:.1f}ms</>",
        )
        raise
    except Exception as error:
        _log_event(
            correlation_id,
            "ERROR",
            "LLM::Agent",
            f"<r>failed</> | category=<y>unexpected</> "
            f"cause=<r>{_safe_log_text(_cause_name(error))}</> "
            f"elapsed=<c>{(perf_counter() - started) * 1000:.1f}ms</>",
        )
        raise

    tool_failures = sum(not item.success for item in result.trace.tool_calls)
    usage = result.usage
    _log_event(
        correlation_id,
        "SUCCESS",
        "LLM::Agent",
        f"<g><b>completed</b></> | model_calls=<c>{result.model_call_count}</> "
        f"tools=<c>{result.tool_call_count}</> "
        f"tool_failures=<y>{tool_failures}</> "
        f"elapsed=<c>{result.elapsed * 1000:.1f}ms</> "
        f"tokens_norm=<c>{usage.prompt_tokens}/{usage.completion_tokens}/{usage.total_tokens}</>",
    )
    return result


async def _run_bounded_conversation(
    *,
    backend: AgentCompletionBackend,
    prompt: ChatInput,
    system_prompt: str | None,
    definitions: tuple[ToolDefinition, ...],
    registry: dict[str, BoundTool[Any, Any]],
    model_alias: str,
    capabilities: ModelCapabilities,
    temperature: float | None,
    limits: AgentLimits,
    started: float,
    correlation_id: str | None,
) -> AgentRunResult:
    history: list[AgentHistoryItem] = []
    model_traces: list[ModelCallTrace] = []
    tool_traces: list[ToolCallTrace] = []
    usage = TokenUsage()
    tool_call_count = 0
    tool_round = 0

    while True:
        if len(model_traces) >= limits.max_model_calls:
            raise LLMRunError(
                category=LLMErrorCategory.LIMITS,
                model_alias=model_alias,
            )

        model_call = len(model_traces) + 1
        _log_event(
            correlation_id,
            "INFO",
            "LLM::Agent",
            f"model_call=<y>{model_call}/{limits.max_model_calls}</> <b>started</> | "
            f"history=<c>models:{len(model_traces)} tools:{len(tool_traces)}</>",
        )
        call_started = perf_counter()
        try:
            turn = await backend.complete_turn(
                prompt=prompt,
                system_prompt=system_prompt,
                history=tuple(history),
                tools=definitions,
                temperature=temperature,
                max_output_tokens=limits.max_output_tokens,
                parallel_tool_calls=capabilities.parallel_tool_calls,
            )
        except asyncio.CancelledError:
            raise
        except LLMServiceError as error:
            _log_event(
                correlation_id,
                "WARNING",
                "LLM::Agent",
                f"model_call=<y>{model_call}/{limits.max_model_calls}</> "
                f"<r>failed</> | "
                f"category=<y>{error.category.value}</> "
                f"cause=<r>{_safe_log_text(_cause_name(error))}</> "
                f"elapsed=<c>{(perf_counter() - call_started) * 1000:.1f}ms</>",
            )
            raise
        except Exception as error:
            _log_event(
                correlation_id,
                "ERROR",
                "LLM::Agent",
                f"model_call=<y>{model_call}/{limits.max_model_calls}</> "
                f"<r>failed</> | category=<y>unexpected</> "
                f"cause=<r>{_safe_log_text(_cause_name(error))}</> "
                f"elapsed=<c>{(perf_counter() - call_started) * 1000:.1f}ms</>",
            )
            raise

        if not isinstance(turn, AgentModelTurn):
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE,
                model_alias=model_alias,
            )
        if turn.model_alias != model_alias:
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE,
                model_alias=model_alias,
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
        finish_reason = _safe_log_text(turn.finish_reason or "none")
        _log_event(
            correlation_id,
            "INFO",
            "LLM::Agent",
            f"model_call=<y>{model_call}/{limits.max_model_calls}</> "
            f"<g>completed</> | finish=<c>{finish_reason}</> "
            f"tool_requests=<c>{len(turn.tool_calls)}</> "
            f"answer_chars=<c>{len(turn.content or "")}</> "
            f"elapsed=<c>{turn.elapsed * 1000:.1f}ms</> "
            f"tokens_norm=<c>{turn.usage.prompt_tokens}/{turn.usage.completion_tokens}/"
            f"{turn.usage.total_tokens}</> cumulative=<c>{usage.prompt_tokens}/"
            f"{usage.completion_tokens}/{usage.total_tokens}</>",
        )

        if not turn.tool_calls:
            if turn.content is None or not turn.content.strip():
                raise LLMRunError(
                    category=LLMErrorCategory.INVALID_RESPONSE,
                    model_alias=model_alias,
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
            raise LLMRunError(
                category=LLMErrorCategory.INVALID_RESPONSE,
                model_alias=model_alias,
            )
        if tool_call_count + len(turn.tool_calls) > limits.max_tool_calls:
            raise LLMRunError(
                category=LLMErrorCategory.LIMITS,
                model_alias=model_alias,
            )

        tool_round += 1
        dispatched = await _dispatch_tool_round(
            turn.tool_calls,
            registry=registry,
            max_parallel_tools=limits.max_parallel_tools,
            max_result_bytes=limits.max_tool_result_bytes,
            correlation_id=correlation_id,
            round_number=tool_round,
            origin_model_call=model_call,
            first_ordinal=tool_call_count + 1,
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
    correlation_id: str | None,
    round_number: int,
    origin_model_call: int,
    first_ordinal: int,
) -> tuple[_DispatchedToolCall, ...]:
    semaphore = asyncio.Semaphore(max_parallel_tools)
    round_started = perf_counter()
    last_ordinal = first_ordinal + len(calls) - 1
    _log_event(
        correlation_id,
        "INFO",
        "LLM::Tools",
        f"round=<y>{round_number}</> origin_model_call=<y>{origin_model_call}</> "
        f"<b>started</> | calls=<c>{len(calls)}</> parallel=<c>{max_parallel_tools}</> "
        f"ordinals=<c>{first_ordinal}-{last_ordinal}</>",
    )

    async def dispatch(index: int, call: AgentToolCall) -> _DispatchedToolCall:
        scheduled = perf_counter()
        async with semaphore:
            queue_elapsed = perf_counter() - scheduled
            ordinal = first_ordinal + index
            _log_event(
                correlation_id,
                "INFO",
                "LLM::Tools",
                f"tool=<y>{ordinal}</> round=<y>{round_number}</> "
                f"slot=<c>{index + 1}/{len(calls)}</> <b>started</> | "
                f"name=<g>{_safe_log_text(call.name)}</> "
                f"queue=<c>{queue_elapsed * 1000:.1f}ms</>",
            )
            return await _dispatch_tool_call(
                call,
                registry=registry,
                max_result_bytes=max_result_bytes,
                correlation_id=correlation_id,
                ordinal=ordinal,
                round_number=round_number,
            )

    async with asyncio.TaskGroup() as task_group:
        tasks = [
            task_group.create_task(dispatch(index, call))
            for index, call in enumerate(calls)
        ]
    results = tuple(task.result() for task in tasks)
    _log_event(
        correlation_id,
        "INFO",
        "LLM::Tools",
        f"round=<y>{round_number}</> <g>completed</> | calls=<c>{len(calls)}</> "
        f"elapsed=<c>{(perf_counter() - round_started) * 1000:.1f}ms</>",
    )
    return results


async def _dispatch_tool_call(
    call: AgentToolCall,
    *,
    registry: dict[str, BoundTool[Any, Any]],
    max_result_bytes: int,
    correlation_id: str | None,
    ordinal: int,
    round_number: int,
) -> _DispatchedToolCall:
    started = perf_counter()
    tool = registry.get(call.name)
    if tool is None:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.UNKNOWN_TOOL,
            summary="unknown tool",
            elapsed=perf_counter() - started,
            correlation_id=correlation_id,
            ordinal=ordinal,
            round_number=round_number,
        )

    try:
        arguments = tool.validate_arguments(call.arguments)
    except ToolArgumentsError as error:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.INVALID_ARGUMENTS,
            summary="invalid arguments",
            elapsed=perf_counter() - started,
            correlation_id=correlation_id,
            ordinal=ordinal,
            round_number=round_number,
            cause_name=type(error).__name__,
        )

    try:
        output = await tool.invoke(arguments)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.EXECUTION,
            summary="handler failed",
            elapsed=perf_counter() - started,
            correlation_id=correlation_id,
            ordinal=ordinal,
            round_number=round_number,
            cause_name=type(error).__name__,
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
            correlation_id=correlation_id,
            ordinal=ordinal,
            round_number=round_number,
            cause_name=type(error).__name__,
        )
    except ToolOutputSerializationError as error:
        return _failed_tool_call(
            call,
            category=ToolErrorCategory.EXECUTION,
            summary="invalid result",
            elapsed=perf_counter() - started,
            correlation_id=correlation_id,
            ordinal=ordinal,
            round_number=round_number,
            cause_name=type(error).__name__,
        )

    elapsed = perf_counter() - started
    reported_error = output.reported_error_code
    diagnostic = (
        ""
        if output.diagnostic is None
        else f" diagnostic=<y>{_safe_log_text(output.diagnostic, 160)}</>"
    )
    if reported_error is None:
        _log_event(
            correlation_id,
            "INFO",
            "LLM::Tools",
            f"tool=<y>{ordinal}</> <g>completed</> | "
            f"name=<g>{_safe_log_text(call.name)}</> "
            f"elapsed=<c>{elapsed * 1000:.1f}ms</> bytes=<c>{result_bytes}</> "
            f"summary=<c>{_safe_log_text(output.summary, 160)}</>{diagnostic}",
        )
    else:
        _log_event(
            correlation_id,
            "WARNING",
            "LLM::Tools",
            f"tool=<y>{ordinal}</> <r>reported error</> | "
            f"name=<g>{_safe_log_text(call.name)}</> "
            f"code=<y>{_safe_log_text(reported_error)}</> "
            f"elapsed=<c>{elapsed * 1000:.1f}ms</> bytes=<c>{result_bytes}</> "
            f"summary=<c>{_safe_log_text(output.summary, 160)}</>{diagnostic}",
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
            success=reported_error is None,
            elapsed=elapsed,
            result_bytes=result_bytes,
            error_category=(
                None if reported_error is None else ToolErrorCategory.REPORTED
            ),
        ),
    )


def _failed_tool_call(
    call: AgentToolCall,
    *,
    category: ToolErrorCategory,
    summary: str,
    elapsed: float,
    correlation_id: str | None,
    ordinal: int,
    round_number: int,
    result_bytes: int = 0,
    cause_name: str | None = None,
) -> _DispatchedToolCall:
    cause = _safe_log_text(cause_name or "none")
    _log_event(
        correlation_id,
        "WARNING",
        "LLM::Tools",
        f"tool=<y>{ordinal}</> round=<y>{round_number}</> <r>failed</> | "
        f"name=<g>{_safe_log_text(call.name)}</> category=<y>{category.value}</> "
        f"cause=<r>{cause}</> elapsed=<c>{elapsed * 1000:.1f}ms</> "
        f"bytes=<c>{result_bytes}</>",
    )
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
