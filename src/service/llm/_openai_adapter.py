"""Narrow OpenAI SDK translation boundary used by the LLM service."""

import asyncio
import json
import re
from collections.abc import Mapping
from copy import deepcopy
from time import perf_counter
from typing import Any

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import TypeAdapter, ValidationError

from .conversation import (
    AgentCompletionBackend,
    AgentHistoryItem,
    AgentModelTurn,
    AgentToolCall,
    AgentToolResult,
)
from .exceptions import LLMErrorCategory, LLMRunError
from .models import (
    ChatInput,
    ImagePart,
    ModelCapabilities,
    ReasoningEffort,
    StructuredOutputMode,
    TextPart,
)
from .runtime import _ModelHandle
from .tools import ToolDefinition
from .usage import CompletionTokensDetails, PromptTokensDetails, TokenUsage

_STRUCTURED_SYSTEM_PROMPT_PREFIX = (
    "Return only valid JSON matching this exact JSON Schema. "
    "Do not wrap the JSON in markdown. JSON Schema: "
)
_FENCE_PATTERN = re.compile(
    r"```(?:[A-Za-z0-9_+.-]+)?[ \t]*\r?\n(?P<body>.*?)\r?\n```",
    flags=re.IGNORECASE | re.DOTALL,
)
_ACTIVE_MODE_MARKERS: dict[str, tuple[str, ...]] = {
    "json_schema": ("json_schema", "json schema"),
    "json_object": ("json_object", "json object"),
}
_UNSUPPORTED_MARKERS = (
    "unsupported",
    "not supported",
    "does not support",
    "unrecognized",
    "unknown parameter",
    "not implemented",
    "not available",
)
_UNSUPPORTED_CODES = {
    "not_supported",
    "unsupported_parameter",
    "unsupported_response_format",
    "unsupported_value",
}


class InvalidSDKResponseError(Exception):
    """The SDK returned a response that violates its advertised shape."""


class StructuredOutputValidationError(Exception):
    """A structured response failed local JSON, envelope, or type validation."""


def build_messages(
    prompt: ChatInput,
    system_prompt: str | None,
    *,
    structured_schema: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt is not None:
        messages.append({"role": "system", "content": system_prompt})
    if structured_schema is not None:
        serialized_schema = json.dumps(
            structured_schema,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        messages.append(
            {
                "role": "system",
                "content": _STRUCTURED_SYSTEM_PROMPT_PREFIX + serialized_schema,
            }
        )

    content: list[dict[str, Any]] = []
    for part in prompt.parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": part.url, "detail": part.detail},
                }
            )
        else:  # ChatInput validates this, but keep the SDK boundary total.
            raise TypeError("unsupported chat input part")
    messages.append({"role": "user", "content": content})
    return messages


async def create_completion(
    client: Any,
    *,
    model_id: str,
    messages: list[dict[str, Any]],
    temperature: float | None,
    max_output_tokens: int | None,
    reasoning_effort: ReasoningEffort | None = None,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    parallel_tool_calls: bool | None = None,
) -> Any:
    request: dict[str, Any] = {"model": model_id, "messages": messages}
    if temperature is not None:
        request["temperature"] = temperature
    if max_output_tokens is not None:
        request["max_completion_tokens"] = max_output_tokens
    if reasoning_effort is not None:
        request["reasoning_effort"] = reasoning_effort
    if response_format is not None:
        request["response_format"] = response_format
    if tools:
        request["tools"] = tools
        if parallel_tool_calls is not None:
            request["parallel_tool_calls"] = parallel_tool_calls
    return await client.chat.completions.create(**request)


class OpenAIAgentCompletionBackend(AgentCompletionBackend):
    """Translate agent turns using one run-scoped immutable model handle."""

    def __init__(self, handle: _ModelHandle) -> None:
        self._handle = handle

    @property
    def model_alias(self) -> str:
        return self._handle.alias

    @property
    def capabilities(self) -> ModelCapabilities:
        return self._handle.capabilities

    async def complete_turn(
        self,
        *,
        prompt: ChatInput,
        system_prompt: str | None,
        history: tuple[AgentHistoryItem, ...],
        tools: tuple[ToolDefinition, ...],
        temperature: float | None,
        reasoning_effort: ReasoningEffort | None,
        max_output_tokens: int,
        parallel_tool_calls: bool,
    ) -> AgentModelTurn:
        handle = self._handle

        messages = build_agent_messages(prompt, system_prompt, history)
        function_tools = build_function_tools(tools)
        started = perf_counter()
        async with handle.semaphore:
            try:
                completion = await create_completion(
                    handle.client,
                    model_id=handle.model_id,
                    messages=messages,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                    reasoning_effort=reasoning_effort,
                    tools=function_tools,
                    parallel_tool_calls=(
                        parallel_tool_calls if function_tools else None
                    ),
                )
                return extract_agent_turn(
                    completion,
                    model_alias=handle.alias,
                    model_id=handle.model_id,
                    elapsed=perf_counter() - started,
                )
            except asyncio.CancelledError:
                raise
            except InvalidSDKResponseError as error:
                raise LLMRunError(
                    category=LLMErrorCategory.INVALID_RESPONSE,
                    model_alias=handle.alias,
                    cause=error,
                ) from error
            except Exception as error:
                category = provider_error_category(error)
                if category is None:
                    raise
                raise LLMRunError(
                    category=category,
                    model_alias=handle.alias,
                    cause=error,
                ) from error


def build_agent_messages(
    prompt: ChatInput,
    system_prompt: str | None,
    history: tuple[AgentHistoryItem, ...],
) -> list[dict[str, Any]]:
    messages = build_messages(prompt, system_prompt, structured_schema=None)
    for item in history:
        if isinstance(item, AgentModelTurn):
            message: dict[str, Any] = {
                "role": "assistant",
                "content": item.content,
            }
            if item.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments,
                        },
                    }
                    for call in item.tool_calls
                ]
            messages.append(message)
        elif isinstance(item, AgentToolResult):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": item.content,
                }
            )
        else:
            raise TypeError("unsupported agent history item")
    return messages


def build_function_tools(
    tools: tuple[ToolDefinition, ...],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for tool in tools:
        if not tool.strict:
            raise ValueError("agent function tools must be strict")
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": deepcopy(tool.parameters),
                    "strict": True,
                },
            }
        )
    return result


def extract_agent_turn(
    completion: Any,
    *,
    model_alias: str,
    model_id: str,
    elapsed: float,
) -> AgentModelTurn:
    choices = _field(completion, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        raise InvalidSDKResponseError("completion has no choices")
    choice = choices[0]
    message = _field(choice, "message")
    if message is None:
        raise InvalidSDKResponseError("completion choice has no message")

    content = _field(message, "content")
    if content is not None and not isinstance(content, str):
        raise InvalidSDKResponseError("assistant content is invalid")

    raw_tool_calls = _field(message, "tool_calls")
    if raw_tool_calls is None:
        raw_tool_calls = ()
    if not isinstance(raw_tool_calls, (list, tuple)):
        raise InvalidSDKResponseError("assistant tool calls are invalid")

    tool_calls: list[AgentToolCall] = []
    for raw_call in raw_tool_calls:
        if _field(raw_call, "type") != "function":
            raise InvalidSDKResponseError("assistant tool call type is invalid")
        function = _field(raw_call, "function")
        call_id = _field(raw_call, "id")
        name = _field(function, "name")
        arguments = _field(function, "arguments")
        if not isinstance(call_id, str):
            raise InvalidSDKResponseError("assistant tool call is invalid")
        if not isinstance(name, str):
            raise InvalidSDKResponseError("assistant tool call is invalid")
        if not isinstance(arguments, str):
            raise InvalidSDKResponseError("assistant tool call is invalid")
        try:
            tool_calls.append(AgentToolCall(id=call_id, name=name, arguments=arguments))
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidSDKResponseError("assistant tool call is invalid") from error

    finish_reason = _field(choice, "finish_reason")
    if finish_reason is not None and not isinstance(finish_reason, str):
        raise InvalidSDKResponseError("completion finish reason is invalid")
    try:
        return AgentModelTurn(
            content=content,
            tool_calls=tuple(tool_calls),
            model_alias=model_alias,
            model_id=model_id,
            usage=normalize_usage(completion),
            elapsed=elapsed,
            finish_reason=finish_reason,
        )
    except InvalidSDKResponseError:
        raise
    except (AttributeError, TypeError, ValueError) as error:
        raise InvalidSDKResponseError("assistant turn is invalid") from error


def make_output_adapter(output_type: object) -> TypeAdapter[Any]:
    return TypeAdapter(output_type)


def make_envelope_schema(output_adapter: TypeAdapter[Any]) -> dict[str, Any]:
    result_schema = output_adapter.json_schema(mode="validation")
    definitions: dict[str, Any] = {}
    for definitions_key in ("$defs", "definitions"):
        value = result_schema.pop(definitions_key, None)
        if value is not None:
            definitions[definitions_key] = value

    envelope_schema: dict[str, Any] = {
        "type": "object",
        "properties": {"result": result_schema},
        "required": ["result"],
        "additionalProperties": False,
        **definitions,
    }
    _make_strict_schema(envelope_schema, root=envelope_schema)
    return envelope_schema


def make_response_format(
    mode: StructuredOutputMode,
    envelope_schema: dict[str, Any],
) -> dict[str, Any] | None:
    if mode is None:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "llm_structured_response",
            "strict": True,
            "schema": envelope_schema,
        },
    }


def _make_strict_schema(
    schema: dict[str, Any],
    *,
    root: dict[str, Any],
) -> None:
    all_of = schema.get("allOf")
    if isinstance(all_of, list) and len(all_of) == 1 and isinstance(all_of[0], dict):
        inherited = deepcopy(all_of[0])
        schema.pop("allOf")
        schema.update({**inherited, **schema})

    reference = schema.get("$ref")
    if isinstance(reference, str) and len(schema) > 1:
        resolved = deepcopy(_resolve_local_ref(root, reference))
        schema.pop("$ref")
        schema.update({**resolved, **schema})

    schema.pop("default", None)

    properties = schema.get("properties")
    if isinstance(properties, dict):
        schema["required"] = list(properties)
        for property_schema in properties.values():
            if isinstance(property_schema, dict):
                _make_strict_schema(property_schema, root=root)

    if schema.get("type") == "object" and "additionalProperties" not in schema:
        schema["additionalProperties"] = False
    additional_properties = schema.get("additionalProperties")
    if isinstance(additional_properties, dict):
        _make_strict_schema(additional_properties, root=root)

    items = schema.get("items")
    if isinstance(items, dict):
        _make_strict_schema(items, root=root)
    elif isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                _make_strict_schema(item, root=root)

    for alternatives_key in ("anyOf", "oneOf", "allOf", "prefixItems"):
        alternatives = schema.get(alternatives_key)
        if isinstance(alternatives, list):
            for alternative in alternatives:
                if isinstance(alternative, dict):
                    _make_strict_schema(alternative, root=root)

    for definitions_key in ("$defs", "definitions"):
        definitions = schema.get(definitions_key)
        if isinstance(definitions, dict):
            for definition in definitions.values():
                if isinstance(definition, dict):
                    _make_strict_schema(definition, root=root)


def _resolve_local_ref(root: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise ValueError("structured schema contains a non-local reference")
    current: Any = root
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, Mapping) or part not in current:
            raise ValueError("structured schema contains an unresolved reference")
        current = current[part]
    if not isinstance(current, dict):
        raise TypeError("structured schema reference is not an object")
    return current


def extract_text(completion: Any) -> str:
    choices = _field(completion, "choices")
    if not isinstance(choices, (list, tuple)) or not choices:
        raise InvalidSDKResponseError("completion has no choices")
    message = _field(choices[0], "message")
    content = _field(message, "content")
    if not isinstance(content, str) or not content.strip():
        raise InvalidSDKResponseError("completion content is empty")
    return content.strip()


def normalize_usage(completion: Any) -> TokenUsage:
    usage = _field(completion, "usage")
    if usage is None:
        return TokenUsage()

    completion_details = _field(usage, "completion_tokens_details")
    prompt_details = _field(usage, "prompt_tokens_details")
    return TokenUsage(
        completion_tokens=_token_count(usage, "completion_tokens"),
        prompt_tokens=_token_count(usage, "prompt_tokens"),
        total_tokens=_token_count(usage, "total_tokens"),
        completion_tokens_details=CompletionTokensDetails(
            accepted_prediction_tokens=_token_count(
                completion_details, "accepted_prediction_tokens"
            ),
            audio_tokens=_token_count(completion_details, "audio_tokens"),
            reasoning_tokens=_token_count(completion_details, "reasoning_tokens"),
            rejected_prediction_tokens=_token_count(
                completion_details, "rejected_prediction_tokens"
            ),
        ),
        prompt_tokens_details=PromptTokensDetails(
            audio_tokens=_token_count(prompt_details, "audio_tokens"),
            cached_tokens=_token_count(prompt_details, "cached_tokens"),
        ),
    )


def normalize_rejected_usage(error: BaseException) -> TokenUsage:
    if not isinstance(error, APIStatusError):
        return TokenUsage()
    body = getattr(error, "body", None)
    usage = _field(body, "usage")
    if usage is None:
        usage = _field(_field(body, "error"), "usage")
    return normalize_usage({"usage": usage})


def parse_structured_output[T](
    text: str,
    output_adapter: TypeAdapter[T],
) -> T:
    candidate = text.strip()
    match = _FENCE_PATTERN.fullmatch(candidate)
    if match is not None:
        candidate = match.group("body").strip()
    try:
        parsed = json.loads(candidate, parse_constant=_reject_json_constant)
    except json.JSONDecodeError, ValueError:
        raise StructuredOutputValidationError("invalid JSON") from None
    if not isinstance(parsed, dict) or set(parsed) != {"result"}:
        raise StructuredOutputValidationError("invalid structured envelope")
    try:
        return output_adapter.validate_python(parsed["result"])
    except ValidationError, TypeError, ValueError:
        raise StructuredOutputValidationError(
            "structured type validation failed"
        ) from None


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant {value}")


def is_response_format_unsupported(
    error: BaseException,
    mode: StructuredOutputMode,
) -> bool:
    if (
        mode is None
        or not isinstance(error, APIStatusError)
        or error.status_code not in {400, 404, 422}
    ):
        return False

    metadata = _error_metadata(error)
    parameter = metadata.get("param", "").lower()
    if parameter and not parameter.startswith("response_format"):
        return False

    code = metadata.get("code", "").lower()
    text = " ".join(
        metadata[name] for name in ("message", "type") if name in metadata
    ).lower()
    mentioned_modes = {
        candidate
        for candidate, markers in _ACTIVE_MODE_MARKERS.items()
        if any(marker in text for marker in markers)
    }
    if mentioned_modes and mode not in mentioned_modes:
        return False

    mentions_response_format = "response_format" in text or "response format" in text
    has_format_association = (
        parameter.startswith("response_format")
        or mentions_response_format
        or mode in mentioned_modes
    )
    has_unsupported_marker = code in _UNSUPPORTED_CODES or any(
        marker in text for marker in _UNSUPPORTED_MARKERS
    )
    return has_format_association and has_unsupported_marker


def provider_error_category(error: BaseException) -> LLMErrorCategory | None:
    if isinstance(error, APIResponseValidationError):
        return LLMErrorCategory.INVALID_RESPONSE
    if isinstance(error, APITimeoutError):
        return LLMErrorCategory.TIMEOUT
    if isinstance(error, (AuthenticationError, PermissionDeniedError)):
        return LLMErrorCategory.AUTHENTICATION
    if isinstance(error, RateLimitError):
        return LLMErrorCategory.RATE_LIMITED
    if isinstance(error, (APIConnectionError, APIStatusError)):
        return LLMErrorCategory.PROVIDER
    return None


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _token_count(value: Any, name: str) -> int:
    count = _field(value, name)
    if count is None:
        return 0
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise InvalidSDKResponseError("invalid token usage")
    return count


def _error_metadata(error: APIStatusError) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for name in ("param", "code", "type", "message"):
        value = getattr(error, name, None)
        if isinstance(value, str):
            metadata[name] = value

    body = getattr(error, "body", None)
    if isinstance(body, Mapping):
        nested = body.get("error")
        sources = (body, nested) if isinstance(nested, Mapping) else (body,)
        for source in sources:
            for name in ("param", "code", "type", "message"):
                value = source.get(name)
                if isinstance(value, str):
                    metadata.setdefault(name, value)
    return metadata
