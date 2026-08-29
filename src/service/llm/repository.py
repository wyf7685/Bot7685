import contextlib
import os
from pathlib import Path
from uuid import uuid4

from nonebot_plugin_localstore import get_plugin_config_file

from .config import LLMConfig


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
        return LLMConfig.model_validate_json(self._file.read_bytes())

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
