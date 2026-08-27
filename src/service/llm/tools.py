import json
import math
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from .models import ImagePart

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list[JSONValue] | dict[str, JSONValue]
type JSONObject = dict[str, JSONValue]

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MAX_DESCRIPTION_CHARS = 1024
_MAX_SUMMARY_CHARS = 160
_ERROR_CODE_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")
_IMAGE_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,96}$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class ToolArgumentsError(ValueError):
    """Arguments were not a strict JSON object accepted by the tool model."""


class ToolOutputSerializationError(ValueError):
    """A tool returned a value that cannot be represented as strict JSON."""


class ToolOutputTooLargeError(ToolOutputSerializationError):
    """A serialized tool result exceeded its configured byte limit."""

    def __init__(self, result_bytes: int) -> None:
        self.result_bytes = result_bytes
        super().__init__("tool output exceeded its byte limit")


@dataclass(frozen=True, slots=True)
class ToolImageAttachment:
    """One bounded image supplied to the model after a tool result."""

    label: str
    part: ImagePart = field(repr=False)
    payload_bytes: int
    width: int
    height: int
    sha256: str

    def __post_init__(self) -> None:
        label = self.label.strip()
        sha256 = self.sha256.strip().lower()
        if not _IMAGE_LABEL_PATTERN.fullmatch(label):
            raise ValueError("tool image label is invalid")
        if not isinstance(self.part, ImagePart):
            raise TypeError("tool image part must be an ImagePart")
        if not self.part.url.startswith("data:image/"):
            raise ValueError("tool images must use data URLs")
        actual_payload_bytes = len(self.part.url.encode("utf-8"))
        if self.payload_bytes != actual_payload_bytes or self.payload_bytes <= 0:
            raise ValueError("tool image payload byte count is invalid")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("tool image dimensions must be positive")
        if not _SHA256_PATTERN.fullmatch(sha256):
            raise ValueError("tool image sha256 is invalid")
        object.__setattr__(self, "label", label)
        object.__setattr__(self, "sha256", sha256)


@dataclass(frozen=True, slots=True)
class ToolOutput:
    """A model-visible JSON value and explicitly safe operational metadata.

    ``summary`` must describe the operation without copying arguments, returned
    payloads, user data, credentials, or exception messages. A non-null
    ``reported_error_code`` marks a handled domain failure returned to the model.
    ``diagnostic`` is optional safe operational metadata written only to logs.
    """

    value: JSONValue
    summary: str = "completed"
    reported_error_code: str | None = None
    diagnostic: str | None = None
    images: tuple[ToolImageAttachment, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "images", tuple(self.images))
        if any(not isinstance(image, ToolImageAttachment) for image in self.images):
            raise TypeError("tool output images contain an unsupported value")
        summary = self.summary.strip()
        if not summary:
            raise ValueError("tool output summary must not be empty")
        if len(summary) > _MAX_SUMMARY_CHARS:
            raise ValueError("tool output summary is too long")
        if any(ord(character) < 32 or ord(character) == 127 for character in summary):
            raise ValueError("tool output summary must be a single printable line")
        object.__setattr__(self, "summary", summary)
        if self.reported_error_code is not None:
            code = self.reported_error_code.strip().lower()
            if not _ERROR_CODE_PATTERN.fullmatch(code):
                raise ValueError("reported error code must be a safe token")
            object.__setattr__(self, "reported_error_code", code)
        if self.diagnostic is not None:
            diagnostic = self.diagnostic.strip()
            if not diagnostic or len(diagnostic) > _MAX_SUMMARY_CHARS:
                raise ValueError("tool diagnostic must contain 1-160 characters")
            if any(
                ord(character) < 32 or ord(character) == 127 for character in diagnostic
            ):
                raise ValueError("tool diagnostic must be a single printable line")
            object.__setattr__(self, "diagnostic", diagnostic)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """The only part of a bound tool exposed to a completion backend."""

    name: str
    description: str
    parameters: JSONObject
    strict: bool = True


@dataclass(frozen=True, slots=True)
class BoundTool[ContextT, ArgumentsT: BaseModel]:
    """A strict argument model bound to private application context and a handler."""

    name: str
    description: str
    arguments_type: type[ArgumentsT]
    context: ContextT = field(repr=False)
    handler: Callable[[ContextT, ArgumentsT], Awaitable[ToolOutput]] = field(repr=False)
    _parameters: JSONObject = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        name = self.name.strip()
        description = self.description.strip()
        if not _NAME_PATTERN.fullmatch(name):
            raise ValueError(
                "tool name must contain 1-64 ASCII letters, digits, underscores, "
                "or hyphens"
            )
        if not description:
            raise ValueError("tool description must not be empty")
        if len(description) > _MAX_DESCRIPTION_CHARS:
            raise ValueError("tool description is too long")
        if not isinstance(self.arguments_type, type) or not issubclass(
            self.arguments_type, BaseModel
        ):
            raise TypeError("arguments_type must be a pydantic BaseModel subclass")
        if not callable(self.handler):
            raise TypeError("tool handler must be callable")

        parameters = strict_json_schema(self.arguments_type)
        if parameters.get("type") != "object":
            raise TypeError("tool arguments must be represented by a JSON object")

        object.__setattr__(self, "name", name)
        object.__setattr__(self, "description", description)
        object.__setattr__(self, "_parameters", parameters)

    @property
    def definition(self) -> ToolDefinition:
        """Return a context-free definition safe to pass to a model backend."""

        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=deepcopy(self._parameters),
        )

    def validate_arguments(self, arguments_json: str) -> ArgumentsT:
        """Parse and strictly validate one model-produced argument object."""

        if not isinstance(arguments_json, str):
            raise ToolArgumentsError("tool arguments must be JSON text")
        try:
            value = json.loads(
                arguments_json,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_non_finite_constant,
            )
        except (json.JSONDecodeError, RecursionError, TypeError, ValueError) as error:
            raise ToolArgumentsError("invalid tool arguments") from error
        if not isinstance(value, dict):
            raise ToolArgumentsError("tool arguments must be a JSON object")
        try:
            return self.arguments_type.model_validate(
                value,
                strict=True,
                extra="forbid",
            )
        except ValidationError as error:
            raise ToolArgumentsError("invalid tool arguments") from error

    async def invoke(self, arguments: ArgumentsT) -> ToolOutput:
        """Invoke the bound handler after argument validation."""

        output = await self.handler(self.context, arguments)
        if not isinstance(output, ToolOutput):
            raise TypeError("tool handlers must return ToolOutput")
        return output

    async def dispatch(self, arguments_json: str) -> ToolOutput:
        """Validate JSON arguments and invoke the bound handler."""

        return await self.invoke(self.validate_arguments(arguments_json))


def strict_json_schema(arguments_type: type[BaseModel]) -> JSONObject:
    """Build a JSON-only schema with closed objects at every nesting level."""

    schema: dict[str, Any] = arguments_type.model_json_schema(mode="validation")
    _close_json_schema_objects(schema)
    try:
        encoded = json.dumps(
            schema,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result = json.loads(encoded)
    except (TypeError, ValueError) as error:
        raise TypeError("tool argument schema is not valid JSON") from error
    if not isinstance(result, dict):
        raise TypeError("tool argument schema must be a JSON object")
    return result


def serialize_tool_output(
    output: ToolOutput,
    *,
    max_bytes: int,
) -> tuple[str, int]:
    """Serialize one output as compact strict JSON and enforce its UTF-8 size."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    try:
        _validate_json_value(output.value, seen=set())
        content = json.dumps(
            output.value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        result_bytes = len(content.encode("utf-8"))
    except (RecursionError, TypeError, UnicodeError, ValueError) as error:
        raise ToolOutputSerializationError("tool output is not strict JSON") from error
    if result_bytes > max_bytes:
        raise ToolOutputTooLargeError(result_bytes)
    return content, result_bytes


def _close_json_schema_objects(value: Any) -> None:
    if isinstance(value, dict):
        if value.get("type") == "object" or "properties" in value:
            value["additionalProperties"] = False
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
        for nested in value.values():
            _close_json_schema_objects(nested)
    elif isinstance(value, list):
        for nested in value:
            _close_json_schema_objects(nested)


def _object_without_duplicate_keys(
    pairs: list[tuple[str, JSONValue]],
) -> dict[str, JSONValue]:
    result: dict[str, JSONValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_finite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _validate_json_value(value: object, *, seen: set[int]) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite JSON number")
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in seen:
            raise ValueError("cyclic JSON value")
        seen.add(identity)
        try:
            for item in value:
                _validate_json_value(item, seen=seen)
        finally:
            seen.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in seen:
            raise ValueError("cyclic JSON value")
        seen.add(identity)
        try:
            for key, item in value.items():
                if not isinstance(key, str):
                    raise TypeError("JSON object keys must be strings")
                _validate_json_value(item, seen=seen)
        finally:
            seen.remove(identity)
        return
    raise TypeError("unsupported JSON value")
