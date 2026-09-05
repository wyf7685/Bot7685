"""Anthropic Messages protocol adapter."""

import asyncio
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from anthropic import (
    APIError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from .._backend import (
    BackendError,
    CompletionReply,
    CompletionRequest,
    CompletionStop,
    InvalidResponseError,
    ModelTurn,
    ToolCall,
    ToolResult,
    UnsupportedStructuredMode,
    UserTurn,
    field_value,
    require_replay,
    token_count,
)
from .._structured import structured_system_prompt
from ..config import AnthropicThinkingConfig, EndpointConfig, EndpointProtocol
from ..exceptions import LLMErrorCategory
from ..models import ChatInputPart, ImagePart, ReasoningEffort, TextPart
from ..tools import ToolDefinition
from ..usage import CompletionTokensDetails, PromptTokensDetails, TokenUsage

_IMAGE_MEDIA_TYPES = frozenset({"image/gif", "image/jpeg", "image/png", "image/webp"})
_BASE64_PAYLOAD_PATTERN = re.compile(
    r"(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"
)
_NATIVE_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})
_UNSUPPORTED_MARKERS = (
    "unsupported",
    "not supported",
    "does not support",
    "not available",
    "not implemented",
    "unknown field",
    "unknown parameter",
    "unrecognized",
)
_INVALID_SCHEMA_MARKERS = (
    "invalid json schema",
    "invalid schema",
    "schema validation",
    "schema must",
    "schema contains",
    "schema keyword",
    "unsupported keyword",
    "output_config.format.schema",
    "output_config format schema",
    "not a valid json schema",
)
_STRUCTURED_UNSUPPORTED_PATTERNS = (
    re.compile(
        r"(?:output_config(?:\.format)?|output format|structured output)"
        r".{0,48}(?:unsupported|not supported|not available|not implemented|"
        r"unknown (?:field|parameter)|unrecognized)"
    ),
    re.compile(
        r"(?:unsupported|not supported|does not support|not available|"
        r"not implemented|unknown (?:field|parameter)|unrecognized).{0,48}"
        r"(?:output_config(?:\.format)?|output format|structured output)"
    ),
    re.compile(
        r"(?:model|endpoint).{0,96}(?:does not support|unsupported|not available)"
        r".{0,96}(?:json_schema|json schema)"
    ),
)


@dataclass(frozen=True, slots=True)
class _AnthropicReplay:
    owner: object = field(repr=False, compare=False)
    model_id: str
    content: tuple[dict[str, Any], ...] = field(repr=False)
    protocol: EndpointProtocol = field(
        default=EndpointProtocol.ANTHROPIC_MESSAGES,
        init=False,
    )


class AnthropicMessagesBackend:
    """Translate provider-neutral requests to Anthropic Messages calls."""

    __slots__ = ("_client", "_closed", "_endpoint", "_owner")

    def __init__(self, endpoint: EndpointConfig) -> None:
        if endpoint.protocol is not EndpointProtocol.ANTHROPIC_MESSAGES:
            raise ValueError("endpoint protocol is not Anthropic Messages")
        self._endpoint = endpoint
        self._client: AsyncAnthropic | None = None
        self._closed = False
        self._owner = object()

    async def complete(
        self,
        model_id: str,
        request: CompletionRequest,
    ) -> CompletionReply:
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id must not be empty")

        structured_mode = (
            request.structured.mode if request.structured is not None else None
        )
        if structured_mode == "json_object":
            raise UnsupportedStructuredMode(structured_mode)

        params = _build_create_params(
            model_id=model_id,
            request=request,
            owner=self._owner,
        )
        client = self._get_client()
        try:
            message = await client.messages.create(**params)
            return _parse_reply(
                message,
                model_id=model_id,
                owner=self._owner,
            )
        except asyncio.CancelledError:
            raise
        except BackendError:
            raise
        except Exception as error:
            if _is_structured_format_unsupported(error, structured_mode):
                raise UnsupportedStructuredMode(
                    "json_schema",
                    usage=_usage_from_error(error),
                    cause=error,
                ) from error
            category = _provider_error_category(error)
            if category is None:
                raise
            raise BackendError(category, cause=error) from error

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        client = self._client
        self._client = None
        if client is not None:
            await client.close()

    def _get_client(self) -> AsyncAnthropic:
        if self._closed:
            raise BackendError(LLMErrorCategory.CONFIGURATION)
        client = self._client
        if client is None:
            client = AsyncAnthropic(
                api_key=self._endpoint.api_key.get_secret_value(),
                base_url=str(self._endpoint.base_url),
                timeout=float(self._endpoint.timeout_seconds),
                max_retries=int(self._endpoint.max_retries),
            )
            self._client = client
        return client


def _build_create_params(
    *,
    model_id: str,
    request: CompletionRequest,
    owner: object,
) -> dict[str, Any]:
    max_tokens = request.max_output_tokens
    if (
        max_tokens is None
        or isinstance(max_tokens, bool)
        or not isinstance(max_tokens, int)
        or max_tokens <= 0
    ):
        raise BackendError(LLMErrorCategory.CONFIGURATION)

    params: dict[str, Any] = {
        "model": model_id,
        "max_tokens": max_tokens,
        "messages": _build_messages(request, owner=owner, model_id=model_id),
    }

    system = _build_system(request)
    if system is not None:
        params["system"] = system

    tools = _build_tools(request.tools)
    if tools:
        params["tools"] = tools
        params["tool_choice"] = {
            "type": "auto",
            "disable_parallel_tool_use": not request.parallel_tool_calls,
        }

    thinking = _build_thinking(
        request.thinking,
        effort=request.reasoning_effort,
        max_tokens=max_tokens,
    )
    if thinking is not None:
        params["thinking"] = thinking

    output_config = _build_output_config(request)
    if output_config:
        params["output_config"] = output_config

    if request.temperature is not None:
        params["extra_body"] = {"temperature": request.temperature}

    return params


def _build_system(request: CompletionRequest) -> str | None:
    parts: list[str] = []
    if request.system_prompt:
        parts.append(request.system_prompt)
    if request.structured is not None:
        parts.append(structured_system_prompt(request.structured.schema))
    return "\n\n".join(parts) if parts else None


def _build_messages(
    request: CompletionRequest,
    *,
    owner: object,
    model_id: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": _build_content_blocks(request.prompt.parts)}
    ]
    history = request.history
    index = 0
    while index < len(history):
        item = history[index]
        if isinstance(item, ModelTurn):
            replay = require_replay(
                item,
                _AnthropicReplay,
                owner=owner,
                model_id=model_id,
            )
            messages.append(
                {
                    "role": "assistant",
                    "content": [deepcopy(block) for block in replay.content],
                }
            )
            index += 1
            continue

        if isinstance(item, ToolResult):
            content: list[dict[str, Any]] = []
            while index < len(history) and isinstance(
                result := history[index], ToolResult
            ):
                content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": result.call_id,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                )
                index += 1
            while index < len(history) and isinstance(
                user_turn := history[index], UserTurn
            ):
                content.extend(_build_content_blocks(user_turn.parts))
                index += 1
            messages.append({"role": "user", "content": content})
            continue

        if isinstance(item, UserTurn):
            messages.append(
                {"role": "user", "content": _build_content_blocks(item.parts)}
            )
            index += 1
            continue

        raise TypeError("unsupported completion history item")
    return messages


def _build_content_blocks(parts: tuple[ChatInputPart, ...]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in parts:
        if isinstance(part, TextPart):
            blocks.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            blocks.append(_build_image_block(part))
        else:
            raise TypeError("unsupported chat input part")
    return blocks


def _build_image_block(part: ImagePart) -> dict[str, Any]:
    if part.detail != "auto":
        raise BackendError(LLMErrorCategory.CAPABILITY)

    value = part.url
    if any(ord(character) <= 32 or ord(character) == 127 for character in value):
        raise BackendError(LLMErrorCategory.CAPABILITY)
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError as error:
        raise BackendError(LLMErrorCategory.CAPABILITY, cause=error) from error
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc and hostname:
        source: dict[str, Any] = {"type": "url", "url": value}
        return {"type": "image", "source": source}

    if not value.lower().startswith("data:image/"):
        raise BackendError(LLMErrorCategory.CAPABILITY)
    try:
        header, payload = value[5:].split(",", 1)
    except ValueError as error:
        raise BackendError(LLMErrorCategory.CAPABILITY, cause=error) from error
    header_parts = header.split(";")
    media_type = header_parts[0].lower()
    if (
        media_type not in _IMAGE_MEDIA_TYPES
        or len(header_parts) != 2
        or header_parts[1].lower() != "base64"
        or not payload
        or _BASE64_PAYLOAD_PATTERN.fullmatch(payload) is None
    ):
        raise BackendError(LLMErrorCategory.CAPABILITY)

    source = {"type": "base64", "media_type": media_type, "data": payload}
    return {"type": "image", "source": source}


def _build_tools(tools: tuple[ToolDefinition, ...]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": deepcopy(tool.parameters),
            "strict": tool.strict,
        }
        for tool in tools
    ]


def _build_thinking(
    thinking: AnthropicThinkingConfig | None,
    *,
    effort: ReasoningEffort | None,
    max_tokens: int,
) -> dict[str, Any] | None:
    if effort == "minimal":
        raise BackendError(LLMErrorCategory.CAPABILITY)
    if thinking is None:
        return None

    thinking_type = thinking.type
    if thinking_type == "enabled":
        budget = thinking.budget_tokens
        if (
            budget is None
            or isinstance(budget, bool)
            or not isinstance(budget, int)
            or budget < 1024
            or budget >= max_tokens
        ):
            raise BackendError(LLMErrorCategory.CONFIGURATION)
        return {"type": "enabled", "budget_tokens": budget}
    if thinking_type == "adaptive":
        return {"type": "adaptive"}
    if thinking_type == "disabled":
        if effort not in {None, "none"}:
            raise BackendError(LLMErrorCategory.CAPABILITY)
        return {"type": "disabled"}
    raise BackendError(LLMErrorCategory.CONFIGURATION)


def _build_output_config(request: CompletionRequest) -> dict[str, Any]:
    output_config: dict[str, Any] = {}
    effort = request.reasoning_effort
    if effort is not None and effort != "none":
        if effort not in _NATIVE_EFFORTS:
            raise BackendError(LLMErrorCategory.CAPABILITY)
        output_config["effort"] = effort

    structured = request.structured
    if structured is not None:
        if structured.mode == "json_schema":
            output_config["format"] = {
                "type": "json_schema",
                "schema": deepcopy(structured.schema),
            }
        elif structured.mode == "json_object" or structured.mode is not None:
            raise UnsupportedStructuredMode(structured.mode)
    return output_config


def _parse_reply(
    message: Any,
    *,
    model_id: str,
    owner: object,
) -> CompletionReply:
    usage = _normalize_usage(field_value(message, "usage"))
    raw_stop_reason = field_value(message, "stop_reason")
    if not isinstance(raw_stop_reason, str):
        raise InvalidResponseError("Anthropic response has no stop reason")
    stop = _completion_stop(raw_stop_reason)
    if stop in {
        CompletionStop.LENGTH,
        CompletionStop.REFUSAL,
        CompletionStop.FAILED,
    }:
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=stop,
            finish_reason=raw_stop_reason,
        )

    raw_content = field_value(message, "content")
    if not isinstance(raw_content, (list, tuple)):
        raise InvalidResponseError("Anthropic response content is invalid")

    replay_blocks: list[dict[str, Any]] = []
    text_blocks: list[str] = []
    raw_tool_uses: list[Any] = []
    for block in raw_content:
        replay_block = _dump_content_block(block)
        block_type = replay_block.get("type")
        if block_type == "text":
            text = field_value(block, "text")
            if not isinstance(text, str):
                raise InvalidResponseError("Anthropic text block is invalid")
            text_blocks.append(text)
        elif block_type == "thinking":
            thinking = field_value(block, "thinking")
            signature = field_value(block, "signature")
            if not isinstance(thinking, str) or not isinstance(signature, str):
                raise InvalidResponseError("Anthropic thinking block is invalid")
        elif block_type == "redacted_thinking":
            if not isinstance(field_value(block, "data"), str):
                raise InvalidResponseError(
                    "Anthropic redacted thinking block is invalid"
                )
        elif block_type == "tool_use":
            raw_tool_uses.append(block)
        else:
            raise InvalidResponseError("unsupported Anthropic content block")
        replay_blocks.append(replay_block)

    tool_calls: tuple[ToolCall, ...] = ()
    if stop is CompletionStop.TOOL_CALLS:
        if not raw_tool_uses:
            raise InvalidResponseError("Anthropic tool-use stop has no tool call")
        tool_calls = tuple(_parse_tool_call(block) for block in raw_tool_uses)
    elif raw_tool_uses:
        raise InvalidResponseError(
            "Anthropic tool call has an inconsistent stop reason"
        )

    content = "".join(text_blocks) if text_blocks else None
    replay = _AnthropicReplay(
        owner=owner,
        model_id=model_id,
        content=tuple(replay_blocks),
    )
    try:
        return CompletionReply(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            stop=stop,
            finish_reason=raw_stop_reason,
            replay=replay,
        )
    except (TypeError, ValueError) as error:
        raise InvalidResponseError("Anthropic response is invalid") from error


def _dump_content_block(block: Any) -> dict[str, Any]:
    if isinstance(block, Mapping):
        dumped = deepcopy(dict(block))
    else:
        model_dump = getattr(block, "model_dump", None)
        if not callable(model_dump):
            raise InvalidResponseError("Anthropic content block is invalid")
        try:
            dumped = model_dump(mode="json", exclude_none=True)
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidResponseError("Anthropic content block is invalid") from error
    if not isinstance(dumped, dict) or not isinstance(dumped.get("type"), str):
        raise InvalidResponseError("Anthropic content block is invalid")
    return dumped


def _parse_tool_call(block: Any) -> ToolCall:
    caller = field_value(block, "caller")
    caller_type = field_value(caller, "type") if caller is not None else None
    toolset_name = field_value(block, "toolset_name")
    if caller_type not in {None, "direct"} or toolset_name is not None:
        raise InvalidResponseError("unsupported Anthropic server tool call")

    call_id = field_value(block, "id")
    name = field_value(block, "name")
    arguments = field_value(block, "input")
    if not isinstance(call_id, str) or not isinstance(name, str):
        raise InvalidResponseError("Anthropic tool call is invalid")
    if not isinstance(arguments, dict):
        raise InvalidResponseError("Anthropic tool input is not an object")
    try:
        _validate_json_value(arguments)
        arguments_json = json.dumps(
            arguments,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        return ToolCall(id=call_id, name=name, arguments=arguments_json)
    except (AttributeError, TypeError, ValueError) as error:
        raise InvalidResponseError("Anthropic tool call is invalid") from error


def _validate_json_value(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object key is not text")
            _validate_json_value(item)
        return
    raise TypeError("value is not strict JSON")


def _completion_stop(stop_reason: str) -> CompletionStop:
    if stop_reason in {"end_turn", "stop_sequence"}:
        return CompletionStop.COMPLETE
    if stop_reason == "tool_use":
        return CompletionStop.TOOL_CALLS
    if stop_reason in {"max_tokens", "model_context_window_exceeded"}:
        return CompletionStop.LENGTH
    if stop_reason == "refusal":
        return CompletionStop.REFUSAL
    if stop_reason == "pause_turn":
        return CompletionStop.FAILED
    raise InvalidResponseError("Anthropic response has an unknown stop reason")


def _normalize_usage(raw_usage: Any) -> TokenUsage:
    if raw_usage is None:
        raise InvalidResponseError("Anthropic response has no usage")
    input_tokens = token_count(raw_usage, "input_tokens")
    cache_read_tokens = token_count(raw_usage, "cache_read_input_tokens")
    cache_creation_tokens = token_count(raw_usage, "cache_creation_input_tokens")
    output_tokens = token_count(raw_usage, "output_tokens")
    output_details = field_value(raw_usage, "output_tokens_details")
    reasoning_tokens = (
        token_count(output_details, "thinking_tokens")
        if output_details is not None
        else 0
    )
    prompt_tokens = input_tokens + cache_read_tokens + cache_creation_tokens
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=output_tokens,
        total_tokens=prompt_tokens + output_tokens,
        prompt_tokens_details=PromptTokensDetails(
            cached_tokens=cache_read_tokens,
            cache_creation_tokens=cache_creation_tokens,
        ),
        completion_tokens_details=CompletionTokensDetails(
            reasoning_tokens=reasoning_tokens,
        ),
    )


def _provider_error_category(error: BaseException) -> LLMErrorCategory | None:
    if isinstance(error, APIResponseValidationError):
        return LLMErrorCategory.INVALID_RESPONSE
    if isinstance(error, APITimeoutError):
        return LLMErrorCategory.TIMEOUT
    if isinstance(error, (AuthenticationError, PermissionDeniedError)):
        return LLMErrorCategory.AUTHENTICATION
    if isinstance(error, RateLimitError):
        return LLMErrorCategory.RATE_LIMITED
    if isinstance(error, APIStatusError) and error.status_code in {408, 504}:
        return LLMErrorCategory.TIMEOUT
    if isinstance(error, APIError):
        return LLMErrorCategory.PROVIDER
    return None


def _is_structured_format_unsupported(
    error: BaseException,
    mode: str | None,
) -> bool:
    if mode != "json_schema" or not isinstance(error, APIStatusError):
        return False
    if error.status_code not in {400, 422}:
        return False

    metadata = _error_metadata(error)
    text = " ".join(
        metadata[name] for name in ("message", "type") if name in metadata
    ).lower()
    if any(marker in text for marker in _INVALID_SCHEMA_MARKERS):
        return False

    parameter = metadata.get("param", "").lower()
    normalized_parameter = parameter.replace("[", ".").replace("]", "").strip(".")
    allowed_parameters = {"output_config", "output_config.format"}
    if normalized_parameter and normalized_parameter not in allowed_parameters:
        return False

    code = metadata.get("code", "").lower()
    has_unsupported_marker = any(marker in text for marker in _UNSUPPORTED_MARKERS)
    has_unsupported_code = "unsupported" in code or code in {
        "not_supported",
        "unknown_parameter",
    }
    if normalized_parameter:
        return has_unsupported_marker or has_unsupported_code
    return any(
        pattern.search(text) is not None for pattern in _STRUCTURED_UNSUPPORTED_PATTERNS
    )


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
                    metadata[name] = value
    return metadata


def _usage_from_error(error: BaseException) -> TokenUsage:
    if not isinstance(error, APIStatusError):
        return TokenUsage()
    body = getattr(error, "body", None)
    usage = field_value(body, "usage")
    if usage is None:
        usage = field_value(field_value(body, "error"), "usage")
    return _normalize_usage(usage) if usage is not None else TokenUsage()


__all__ = ["AnthropicMessagesBackend"]
