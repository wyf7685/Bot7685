"""Provider-neutral structured-output schema and validation helpers."""

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import TypeAdapter, ValidationError

_STRUCTURED_SYSTEM_PROMPT_PREFIX = (
    "Return only valid JSON matching this exact JSON Schema. "
    "Do not wrap the JSON in markdown. JSON Schema: "
)
_FENCE_PATTERN = re.compile(
    r"```(?:[A-Za-z0-9_+.-]+)?[ \t]*\r?\n(?P<body>.*?)\r?\n```",
    flags=re.IGNORECASE | re.DOTALL,
)


class StructuredOutputValidationError(Exception):
    """A structured response failed local JSON, envelope, or type validation."""


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


def structured_system_prompt(schema: dict[str, Any]) -> str:
    serialized_schema = json.dumps(
        schema,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _STRUCTURED_SYSTEM_PROMPT_PREFIX + serialized_schema


def parse_structured_output[T](text: str, output_adapter: TypeAdapter[T]) -> T:
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


def _make_strict_schema(schema: dict[str, Any], *, root: dict[str, Any]) -> None:
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


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant {value}")


__all__ = [
    "StructuredOutputValidationError",
    "make_envelope_schema",
    "make_output_adapter",
    "parse_structured_output",
    "structured_system_prompt",
]
