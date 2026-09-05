"""OpenAI Responses protocol adapter."""

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from openai import AsyncOpenAI
from openai.types.responses import Response
from openai.types.responses.function_tool_param import FunctionToolParam
from openai.types.responses.response_create_params import (
    ResponseCreateParamsNonStreaming,
)
from openai.types.responses.response_format_text_config_param import (
    ResponseFormatTextConfigParam,
)
from openai.types.responses.response_function_tool_call import (
    ResponseFunctionToolCall,
)
from openai.types.responses.response_input_message_content_list_param import (
    ResponseInputMessageContentListParam,
)
from openai.types.responses.response_input_param import (
    FunctionCallOutput,
    Message,
    ResponseInputItemParam,
    ResponseInputParam,
)
from openai.types.responses.response_output_message import ResponseOutputMessage
from openai.types.responses.response_output_refusal import ResponseOutputRefusal
from openai.types.responses.response_output_text import ResponseOutputText
from openai.types.responses.response_reasoning_item import ResponseReasoningItem
from openai.types.responses.response_text_config_param import ResponseTextConfigParam
from openai.types.responses.tool_param import ToolParam

from .._backend import (
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

_SUPPORTED_OUTPUT_ITEM_TYPES = {"message", "reasoning", "function_call"}


@dataclass(frozen=True, slots=True)
class _OpenAIResponsesReplay:
    owner: object
    model_id: str
    item_json: tuple[str, ...] = field(repr=False)
    protocol: EndpointProtocol = field(
        init=False,
        default=EndpointProtocol.OPENAI_RESPONSES,
    )


class OpenAIResponsesBackend:
    """One lazy OpenAI Responses client bound to an endpoint."""

    def __init__(self, endpoint: EndpointConfig) -> None:
        if endpoint.protocol is not EndpointProtocol.OPENAI_RESPONSES:
            raise ValueError("endpoint protocol is not OpenAI Responses")
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
        input_items = _build_response_input(
            model_id=model_id,
            request=request,
            owner=self._owner,
        )
        tools = _build_response_tools(request.tools)
        params: ResponseCreateParamsNonStreaming = {
            "model": model_id,
            "input": input_items,
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "stream": False,
        }
        instructions = _build_instructions(request)
        if instructions is not None:
            params["instructions"] = instructions
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            params["max_output_tokens"] = request.max_output_tokens
        if request.reasoning_effort is not None:
            params["reasoning"] = {"effort": request.reasoning_effort}
        if request.structured is not None:
            response_format = _make_responses_format(
                request.structured.mode,
                request.structured.schema,
            )
            if response_format is not None:
                text_config: ResponseTextConfigParam = {"format": response_format}
                params["text"] = text_config
        if tools:
            params["tools"] = tools
            params["parallel_tool_calls"] = request.parallel_tool_calls

        try:
            response = await client.responses.create(**params)
            try:
                return _normalize_response(
                    response,
                    owner=self._owner,
                    model_id=model_id,
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise InvalidResponseError("malformed Responses payload") from error
        except asyncio.CancelledError:
            raise
        except InvalidResponseError, UnsupportedStructuredMode:
            raise
        except Exception as error:
            structured = request.structured
            if structured is not None and is_structured_mode_unsupported(
                error,
                structured.mode,
                parameter="text.format",
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
            raise RuntimeError("OpenAI Responses backend is closed")
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


def _build_instructions(request: CompletionRequest) -> str | None:
    instructions: list[str] = []
    if request.system_prompt is not None:
        instructions.append(request.system_prompt)
    if request.structured is not None:
        instructions.append(structured_system_prompt(request.structured.schema))
    return "\n\n".join(instructions) if instructions else None


def _build_response_input(
    *,
    model_id: str,
    request: CompletionRequest,
    owner: object,
) -> ResponseInputParam:
    items: list[ResponseInputItemParam] = [
        _make_user_message(request.prompt.parts),
    ]
    for item in request.history:
        if isinstance(item, ModelTurn):
            replay = require_replay(
                item,
                _OpenAIResponsesReplay,
                owner=owner,
                model_id=model_id,
            )
            items.extend(_decode_response_replay(replay))
        elif isinstance(item, ToolResult):
            result: FunctionCallOutput = {
                "type": "function_call_output",
                "call_id": item.call_id,
                "name": item.name,
                "output": item.content,
            }
            items.append(result)
        elif isinstance(item, UserTurn):
            items.append(_make_user_message(item.parts))
        else:
            raise TypeError("unsupported completion history item")
    return items


def _make_user_message(parts: tuple[ChatInputPart, ...]) -> Message:
    content: ResponseInputMessageContentListParam = []
    for part in parts:
        if isinstance(part, TextPart):
            content.append({"type": "input_text", "text": part.text})
        elif isinstance(part, ImagePart):
            content.append(
                {
                    "type": "input_image",
                    "image_url": part.url,
                    "detail": part.detail,
                }
            )
        else:
            raise TypeError("unsupported chat input part")
    return {"type": "message", "role": "user", "content": content}


def _build_response_tools(tools: tuple[ToolDefinition, ...]) -> list[ToolParam]:
    result: list[ToolParam] = []
    for tool in tools:
        if not tool.strict:
            raise ValueError("OpenAI function tools must be strict")
        function_tool: FunctionToolParam = {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": cast("dict[str, object]", deepcopy(tool.parameters)),
            "strict": True,
        }
        result.append(function_tool)
    return result


def _make_responses_format(
    mode: StructuredOutputMode,
    schema: dict[str, Any],
) -> ResponseFormatTextConfigParam | None:
    if mode is None:
        return None
    if mode == "json_object":
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": "llm_structured_response",
        "strict": True,
        "schema": cast("dict[str, object]", deepcopy(schema)),
    }


def _normalize_response(
    response: Response,
    *,
    owner: object,
    model_id: str,
) -> CompletionReply:
    usage = normalize_openai_usage(response)
    status = response.status
    if status == "incomplete":
        reason = field_value(response.incomplete_details, "reason")
        if reason == "content_filter":
            stop = CompletionStop.REFUSAL
        elif reason == "max_output_tokens":
            stop = CompletionStop.LENGTH
        else:
            stop = CompletionStop.FAILED
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=stop,
            finish_reason=reason if isinstance(reason, str) else status,
        )
    if status in {"failed", "cancelled"}:
        code = field_value(response.error, "code")
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=CompletionStop.FAILED,
            finish_reason=code if isinstance(code, str) else status,
        )
    if status in {"in_progress", "queued"}:
        raise InvalidResponseError("non-streaming response is not terminal")
    if status != "completed":
        raise InvalidResponseError("response status is invalid")
    if response.error is not None:
        raise InvalidResponseError("completed response contains an error")

    texts: list[str] = []
    calls: list[ToolCall] = []
    replay_items: list[str] = []
    refused = False
    for output in response.output:
        output_type = output.type
        item_status = field_value(output, "status")
        if item_status not in {None, "completed"}:
            raise InvalidResponseError("response contains an incomplete output item")

        if isinstance(output, ResponseOutputMessage):
            if output.role != "assistant":
                raise InvalidResponseError(
                    "response output message has an invalid role"
                )
            for content in output.content:
                if isinstance(content, ResponseOutputText):
                    texts.append(content.text)
                elif isinstance(content, ResponseOutputRefusal):
                    refused = True
                else:
                    raise InvalidResponseError(
                        "response message contains unsupported semantic output"
                    )
        elif isinstance(output, ResponseReasoningItem):
            encrypted_content = output.encrypted_content
            if not isinstance(encrypted_content, str) or not encrypted_content:
                raise InvalidResponseError(
                    "reasoning output omitted encrypted replay content"
                )
        elif isinstance(output, ResponseFunctionToolCall):
            try:
                calls.append(
                    ToolCall(
                        id=output.call_id,
                        name=output.name,
                        arguments=output.arguments,
                    )
                )
            except (AttributeError, TypeError, ValueError) as error:
                raise InvalidResponseError("invalid Responses function call") from error
        else:
            raise InvalidResponseError(
                f"unsupported Responses output item type: {output_type}"
            )

        replay_items.append(_serialize_response_item(output))

    if refused:
        return CompletionReply(
            content=None,
            tool_calls=(),
            usage=usage,
            stop=CompletionStop.REFUSAL,
            finish_reason="refusal",
        )

    content = "".join(texts).strip()
    normalized_content = content or None
    if calls:
        stop = CompletionStop.TOOL_CALLS
    else:
        if normalized_content is None:
            raise InvalidResponseError("response content is empty")
        stop = CompletionStop.COMPLETE

    return CompletionReply(
        content=normalized_content,
        tool_calls=tuple(calls),
        usage=usage,
        stop=stop,
        finish_reason=status,
        replay=_OpenAIResponsesReplay(
            owner=owner,
            model_id=model_id,
            item_json=tuple(replay_items),
        ),
    )


def _serialize_response_item(item: object) -> str:
    dumper = getattr(item, "model_dump", None)
    if not callable(dumper):
        raise InvalidResponseError("response output item cannot be replayed")
    payload = dumper(mode="json", exclude_none=True)
    if not isinstance(payload, dict):
        raise InvalidResponseError("response output item cannot be replayed")
    try:
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise InvalidResponseError("response output item is not valid JSON") from error


def _decode_response_replay(
    replay: _OpenAIResponsesReplay,
) -> list[ResponseInputItemParam]:
    items: list[ResponseInputItemParam] = []
    for item_json in replay.item_json:
        try:
            payload: object = json.loads(item_json)
        except json.JSONDecodeError as error:
            raise InvalidResponseError("Responses replay is invalid") from error
        if not isinstance(payload, dict):
            raise InvalidResponseError("Responses replay is invalid")
        item_type = payload.get("type")
        if item_type not in _SUPPORTED_OUTPUT_ITEM_TYPES:
            raise InvalidResponseError("Responses replay contains an unsupported item")
        items.append(cast("ResponseInputItemParam", payload))
    return items


__all__ = ["OpenAIResponsesBackend"]
