"""OpenAI Chat Completions protocol adapter."""

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion
from openai.types.chat.chat_completion_assistant_message_param import (
    ChatCompletionAssistantMessageParam,
)
from openai.types.chat.chat_completion_content_part_param import (
    ChatCompletionContentPartParam,
)
from openai.types.chat.chat_completion_function_tool_param import (
    ChatCompletionFunctionToolParam,
)
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
)
from openai.types.chat.chat_completion_message_param import ChatCompletionMessageParam
from openai.types.chat.chat_completion_tool_union_param import (
    ChatCompletionToolUnionParam,
)
from openai.types.chat.completion_create_params import (
    CompletionCreateParamsNonStreaming,
    ResponseFormat,
)
from openai.types.shared_params.function_definition import FunctionDefinition

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
    require_replay,
)
from .._structured import structured_system_prompt
from ..config import EndpointConfig, EndpointProtocol
from ..models import ChatInputPart, ImagePart, StructuredOutputMode, TextPart
from ..tools import ToolDefinition
from ._openai import (
    is_structured_mode_unsupported,
    normalize_openai_usage,
    normalize_rejected_usage,
    openai_backend_error,
)


@dataclass(frozen=True, slots=True)
class _OpenAICompletionReplay:
    owner: object
    model_id: str
    message_json: str = field(repr=False)
    protocol: EndpointProtocol = field(
        init=False,
        default=EndpointProtocol.OPENAI_COMPLETIONS,
    )


class OpenAICompletionBackend:
    """One lazy OpenAI Chat Completions client bound to an endpoint."""

    def __init__(self, endpoint: EndpointConfig) -> None:
        if endpoint.protocol is not EndpointProtocol.OPENAI_COMPLETIONS:
            raise ValueError("endpoint protocol is not OpenAI Chat Completions")
        self._endpoint = endpoint
        self._client: AsyncOpenAI | None = None
        self._closed = False
        self._owner = object()

    async def complete(
        self,
        model_id: str,
        request: CompletionRequest,
    ) -> CompletionReply:
        client = self._get_client()
        messages = _build_chat_messages(
            model_id=model_id,
            request=request,
            owner=self._owner,
        )
        tools = _build_chat_tools(request.tools)
        params: CompletionCreateParamsNonStreaming = {
            "model": model_id,
            "messages": messages,
            "stream": False,
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            params["max_completion_tokens"] = request.max_output_tokens
        if request.reasoning_effort is not None:
            params["reasoning_effort"] = request.reasoning_effort
        if request.structured is not None:
            response_format = _make_chat_response_format(
                request.structured.mode,
                request.structured.schema,
            )
            if response_format is not None:
                params["response_format"] = response_format
        if tools:
            params["tools"] = tools
            params["parallel_tool_calls"] = request.parallel_tool_calls

        try:
            completion = await client.chat.completions.create(**params)
            try:
                return _normalize_chat_completion(
                    completion,
                    owner=self._owner,
                    model_id=model_id,
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise InvalidResponseError(
                    "malformed Chat Completions payload"
                ) from error
        except asyncio.CancelledError:
            raise
        except BackendError:
            raise
        except Exception as error:
            structured = request.structured
            if structured is not None and is_structured_mode_unsupported(
                error,
                structured.mode,
                parameter="response_format",
            ):
                raise UnsupportedStructuredMode(
                    structured.mode,
                    usage=normalize_rejected_usage(error),
                    cause=error,
                ) from error
            converted = openai_backend_error(error)
            if converted is None:
                raise
            raise converted from error

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        client = self._client
        self._client = None
        if client is not None:
            await client.close()

    def _get_client(self) -> AsyncOpenAI:
        if self._closed:
            raise RuntimeError("OpenAI completion backend is closed")
        client = self._client
        if client is not None:
            return client
        endpoint = self._endpoint
        created = AsyncOpenAI(
            api_key=endpoint.api_key.get_secret_value(),
            base_url=str(endpoint.base_url),
            timeout=float(endpoint.timeout_seconds),
            max_retries=int(endpoint.max_retries),
        )
        self._client = created
        return created


def _build_chat_messages(
    *,
    model_id: str,
    request: CompletionRequest,
    owner: object,
) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = []
    if request.system_prompt is not None:
        messages.append({"role": "system", "content": request.system_prompt})
    if request.structured is not None:
        messages.append(
            {
                "role": "system",
                "content": structured_system_prompt(request.structured.schema),
            }
        )
    messages.append(
        {
            "role": "user",
            "content": _build_chat_content(request.prompt.parts),
        }
    )

    for item in request.history:
        if isinstance(item, ModelTurn):
            replay = require_replay(
                item,
                _OpenAICompletionReplay,
                owner=owner,
                model_id=model_id,
            )
            messages.append(_decode_chat_replay(replay))
        elif isinstance(item, ToolResult):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": item.content,
                }
            )
        elif isinstance(item, UserTurn):
            messages.append(
                {
                    "role": "user",
                    "content": _build_chat_content(item.parts),
                }
            )
        else:
            raise TypeError("unsupported completion history item")
    return messages


def _build_chat_content(
    parts: tuple[ChatInputPart, ...],
) -> list[ChatCompletionContentPartParam]:
    content: list[ChatCompletionContentPartParam] = []
    for part in parts:
        if isinstance(part, TextPart):
            content.append({"type": "text", "text": part.text})
        elif isinstance(part, ImagePart):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": part.url, "detail": part.detail},
                }
            )
        else:
            raise TypeError("unsupported chat input part")
    return content


def _build_chat_tools(
    tools: tuple[ToolDefinition, ...],
) -> list[ChatCompletionToolUnionParam]:
    result: list[ChatCompletionToolUnionParam] = []
    for tool in tools:
        if not tool.strict:
            raise ValueError("OpenAI function tools must be strict")
        function: FunctionDefinition = {
            "name": tool.name,
            "description": tool.description,
            "parameters": cast("dict[str, object]", deepcopy(tool.parameters)),
            "strict": True,
        }
        function_tool: ChatCompletionFunctionToolParam = {
            "type": "function",
            "function": function,
        }
        result.append(function_tool)
    return result


def _make_chat_response_format(
    mode: StructuredOutputMode,
    schema: dict[str, Any],
) -> ResponseFormat | None:
    if mode is None:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "llm_structured_response",
            "strict": True,
            "schema": cast("dict[str, object]", deepcopy(schema)),
        },
    }


def _normalize_chat_completion(
    completion: ChatCompletion,
    *,
    owner: object,
    model_id: str,
) -> CompletionReply:
    if not completion.choices:
        raise InvalidResponseError("completion has no choices")
    choice = completion.choices[0]
    message = choice.message
    finish_reason = choice.finish_reason
    usage = normalize_openai_usage(completion)

    if message.refusal:
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=CompletionStop.REFUSAL,
            finish_reason=finish_reason,
        )
    if finish_reason == "content_filter":
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=CompletionStop.REFUSAL,
            finish_reason=finish_reason,
        )
    if finish_reason == "length":
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=CompletionStop.LENGTH,
            finish_reason=finish_reason,
        )
    if finish_reason not in {"stop", "tool_calls"}:
        raise InvalidResponseError("unsupported completion finish reason")
    if message.audio is not None:
        raise InvalidResponseError("audio output is not supported")
    if message.function_call is not None:
        raise InvalidResponseError("legacy function-call output is not supported")
    if message.annotations:
        raise InvalidResponseError("annotated hosted-tool output is not supported")

    content = message.content.strip() if message.content is not None else None
    if content == "":
        content = None
    raw_tool_calls = message.tool_calls or []
    if finish_reason == "stop":
        if raw_tool_calls:
            raise InvalidResponseError("completion stopped with unexpected tool calls")
        if content is None:
            raise InvalidResponseError("completion content is empty")
        stop = CompletionStop.COMPLETE
        tool_calls: tuple[ToolCall, ...] = ()
    else:
        if not raw_tool_calls:
            raise InvalidResponseError("completion omitted requested tool calls")
        parsed_calls: list[ToolCall] = []
        for raw_call in raw_tool_calls:
            if not isinstance(raw_call, ChatCompletionMessageFunctionToolCall):
                raise InvalidResponseError("unsupported completion tool-call type")
            try:
                parsed_calls.append(
                    ToolCall(
                        id=raw_call.id,
                        name=raw_call.function.name,
                        arguments=raw_call.function.arguments,
                    )
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise InvalidResponseError("invalid completion tool call") from error
        tool_calls = tuple(parsed_calls)
        stop = CompletionStop.TOOL_CALLS

    payload = message.model_dump(mode="json", exclude_none=True)
    try:
        message_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise InvalidResponseError("assistant replay is not valid JSON") from error
    return CompletionReply(
        content=content,
        tool_calls=tool_calls,
        usage=usage,
        stop=stop,
        finish_reason=finish_reason,
        replay=_OpenAICompletionReplay(
            owner=owner,
            model_id=model_id,
            message_json=message_json,
        ),
    )


def _decode_chat_replay(
    replay: _OpenAICompletionReplay,
) -> ChatCompletionAssistantMessageParam:
    try:
        payload: object = json.loads(replay.message_json)
    except json.JSONDecodeError as error:
        raise InvalidResponseError("assistant replay is invalid") from error
    if not isinstance(payload, dict) or payload.get("role") != "assistant":
        raise InvalidResponseError("assistant replay is invalid")
    return cast("ChatCompletionAssistantMessageParam", payload)


__all__ = ["OpenAICompletionBackend"]
