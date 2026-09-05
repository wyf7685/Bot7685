from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)

from .._backend import BackendError, field_value, token_count
from ..exceptions import LLMErrorCategory
from ..models import StructuredOutputMode
from ..usage import CompletionTokensDetails, PromptTokensDetails, TokenUsage

_ACTIVE_MODE_MARKERS: dict[str, tuple[str, ...]] = {
    "json_schema": ("json_schema", "json schema"),
    "json_object": ("json_object", "json object"),
}
_UNSUPPORTED_MARKERS = (
    "unsupported",
    "not supported",
    "isn't supported",
    "does not support",
    "cannot be used",
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
_INVALID_SCHEMA_CODES = {
    "invalid_json_schema",
    "invalid_schema",
    "json_schema_validation_error",
    "schema_validation_error",
}
_INVALID_SCHEMA_MARKERS = (
    "invalid json schema",
    "invalid schema",
    "schema is invalid",
    "schema keyword",
    "schema validation",
)


def is_structured_mode_unsupported(
    error: BaseException,
    mode: StructuredOutputMode,
    *,
    parameter: str,
) -> bool:
    if (
        mode is None
        or not isinstance(error, APIStatusError)
        or error.status_code not in {400, 404, 422}
    ):
        return False

    metadata = error_metadata(error)
    code = metadata.get("code", "").lower()
    text = " ".join(
        metadata[name] for name in ("message", "type") if name in metadata
    ).lower()
    if code in _INVALID_SCHEMA_CODES or any(
        marker in text for marker in _INVALID_SCHEMA_MARKERS
    ):
        return False

    raw_parameter = metadata.get("param", "").lower()
    normalized_parameter = raw_parameter.replace("[", ".").replace("]", "").strip(".")
    allowed_parameters = {parameter, f"{parameter}.type", f"{parameter}.strict"}
    if parameter == "response_format":
        allowed_parameters.add("response_format.json_schema")
        allowed_parameters.add("response_format.json_schema.strict")
    if normalized_parameter and normalized_parameter not in allowed_parameters:
        return False

    mentioned_modes = {
        candidate
        for candidate, markers in _ACTIVE_MODE_MARKERS.items()
        if any(marker in text for marker in markers)
    }
    if mentioned_modes and mode not in mentioned_modes:
        return False

    parameter_markers = {parameter, parameter.replace(".", " ")}
    if parameter == "response_format":
        parameter_markers.add("response format")
    has_format_association = (
        bool(normalized_parameter)
        or any(marker in text for marker in parameter_markers)
        or mode in mentioned_modes
    )
    has_unsupported_marker = code in _UNSUPPORTED_CODES or any(
        marker in text for marker in _UNSUPPORTED_MARKERS
    )
    return has_format_association and has_unsupported_marker


def normalize_openai_usage(value: object) -> TokenUsage:
    usage = field_value(value, "usage")
    if usage is None:
        return TokenUsage()

    prompt_name = (
        "prompt_tokens"
        if field_value(usage, "prompt_tokens") is not None
        else "input_tokens"
    )
    completion_name = (
        "completion_tokens"
        if field_value(usage, "completion_tokens") is not None
        else "output_tokens"
    )
    prompt_details = field_value(usage, "prompt_tokens_details")
    if prompt_details is None:
        prompt_details = field_value(usage, "input_tokens_details")
    completion_details = field_value(usage, "completion_tokens_details")
    if completion_details is None:
        completion_details = field_value(usage, "output_tokens_details")
    prompt_tokens = token_count(usage, prompt_name)
    completion_tokens = token_count(usage, completion_name)
    total_tokens = (
        token_count(usage, "total_tokens")
        if field_value(usage, "total_tokens") is not None
        else prompt_tokens + completion_tokens
    )

    return TokenUsage(
        completion_tokens=completion_tokens,
        prompt_tokens=prompt_tokens,
        total_tokens=total_tokens,
        completion_tokens_details=CompletionTokensDetails(
            accepted_prediction_tokens=token_count(
                completion_details,
                "accepted_prediction_tokens",
            ),
            audio_tokens=token_count(completion_details, "audio_tokens"),
            reasoning_tokens=token_count(completion_details, "reasoning_tokens"),
            rejected_prediction_tokens=token_count(
                completion_details,
                "rejected_prediction_tokens",
            ),
        ),
        prompt_tokens_details=PromptTokensDetails(
            audio_tokens=token_count(prompt_details, "audio_tokens"),
            cached_tokens=token_count(prompt_details, "cached_tokens"),
            cache_creation_tokens=token_count(prompt_details, "cache_write_tokens"),
        ),
    )


def normalize_rejected_usage(error: BaseException) -> TokenUsage:
    if not isinstance(error, APIStatusError):
        return TokenUsage()
    body = error.body
    usage = field_value(body, "usage")
    if usage is None:
        usage = field_value(field_value(body, "error"), "usage")
    if usage is None:
        # The SDK unwraps the error object and omits its sibling usage field.
        try:
            response_body = error.response.json()
        except ValueError:
            return TokenUsage()
        usage = field_value(response_body, "usage")
        if usage is None:
            usage = field_value(field_value(response_body, "error"), "usage")
    return normalize_openai_usage({"usage": usage})


def openai_backend_error(error: BaseException) -> BackendError | None:
    if isinstance(error, APIResponseValidationError):
        return BackendError(LLMErrorCategory.INVALID_RESPONSE, cause=error)
    if isinstance(error, APITimeoutError):
        return BackendError(LLMErrorCategory.TIMEOUT, cause=error)
    if isinstance(error, (AuthenticationError, PermissionDeniedError)):
        return BackendError(LLMErrorCategory.AUTHENTICATION, cause=error)
    if isinstance(error, RateLimitError):
        return BackendError(LLMErrorCategory.RATE_LIMITED, cause=error)
    if isinstance(error, (APIConnectionError, APIStatusError)):
        return BackendError(LLMErrorCategory.PROVIDER, cause=error)
    return None


def error_metadata(error: APIStatusError) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for name in ("param", "code", "type", "message"):
        value = getattr(error, name, None)
        if isinstance(value, str):
            metadata[name] = value

    body = error.body
    if isinstance(body, dict):
        nested = body.get("error")
        sources = (body, nested) if isinstance(nested, dict) else (body,)
        for source in sources:
            for name in ("param", "code", "type", "message"):
                value = source.get(name)
                if isinstance(value, str):
                    metadata.setdefault(name, value)
    return metadata
