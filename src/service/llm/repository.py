import contextlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from nonebot_plugin_localstore import get_plugin_config_file

from .config import EndpointProtocol, LLMConfig

_LEGACY_CONFIG_FIELDS = {"active_model", "endpoints", "models"}
_LEGACY_ENDPOINT_FIELDS = {
    "base_url",
    "api_key",
    "timeout_seconds",
    "max_retries",
}
_LEGACY_MODEL_FIELDS = {
    "endpoint",
    "model",
    "max_concurrent",
    "capabilities",
    "selectable",
}
_LEGACY_CAPABILITY_FIELDS = {
    "tools",
    "vision",
    "reasoning_efforts",
    "structured_output_modes",
    "parallel_tool_calls",
}


def _is_complete_legacy_config(value: object) -> bool:
    if not isinstance(value, dict) or value.keys() != _LEGACY_CONFIG_FIELDS:
        return False
    endpoints = value.get("endpoints")
    models = value.get("models")
    if not isinstance(endpoints, dict) or not isinstance(models, dict):
        return False
    if not endpoints or not models:
        return False
    if any(
        not isinstance(endpoint, dict) or endpoint.keys() != _LEGACY_ENDPOINT_FIELDS
        for endpoint in endpoints.values()
    ):
        return False
    return all(
        isinstance(model, dict)
        and model.keys() == _LEGACY_MODEL_FIELDS
        and isinstance(model.get("capabilities"), dict)
        and model["capabilities"].keys() == _LEGACY_CAPABILITY_FIELDS
        for model in models.values()
    )


def _migrate_legacy_config(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_model": value["active_model"],
        "endpoints": {
            alias: {
                **endpoint,
                "protocol": EndpointProtocol.OPENAI_COMPLETIONS.value,
            }
            for alias, endpoint in value["endpoints"].items()
        },
        "models": {
            alias: {
                **model,
                "capabilities": {
                    **model["capabilities"],
                    "temperature": True,
                },
            }
            for alias, model in value["models"].items()
        },
    }


class LLMConfigRepository:
    """Persist the complete LLM configuration in the service config directory."""

    def __init__(self) -> None:
        self._file = get_plugin_config_file("config.json")

    @property
    def file(self) -> Path:
        return self._file

    def load(self) -> LLMConfig | None:
        if not self._file.exists():
            return None
        raw = json.loads(self._file.read_bytes())
        if not _is_complete_legacy_config(raw):
            return LLMConfig.model_validate(raw)
        config = LLMConfig.model_validate(_migrate_legacy_config(raw))
        self.save(config)
        return config

    def save(self, config: LLMConfig) -> None:
        payload = config.model_dump_json(
            indent=2,
            context={"persist_secrets": True},
        ).encode()
        temporary = self._file.with_name(f".{self._file.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            if os.name != "nt":
                temporary.chmod(0o600)
            temporary.replace(self._file)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()

    def delete(self) -> None:
        self._file.unlink(missing_ok=True)


__all__ = ["LLMConfigRepository"]
