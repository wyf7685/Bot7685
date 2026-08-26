from __future__ import annotations

from collections.abc import Collection

from anyio import Lock
from msgspec import DecodeError
from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.utils import ConfigModelFile

from .exceptions import LLMModelSelectionError


class _ActiveModelState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    active_model: str = Field(min_length=1)

    @field_validator("active_model")
    @classmethod
    def validate_active_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("active_model must not be empty")
        return value


class ActiveModelStore:
    """Process-local active-model state persisted in the LLM data directory."""

    def __init__(
        self,
        *,
        default_alias: str,
        configured_aliases: Collection[str],
        selectable_aliases: Collection[str],
        repository: ConfigModelFile[_ActiveModelState] | None = None,
    ) -> None:
        default_alias = default_alias.strip()
        configured = frozenset(configured_aliases)
        selectable = frozenset(selectable_aliases)
        if default_alias not in configured or default_alias not in selectable:
            raise ValueError("default model must be configured and selectable")
        if not selectable or not selectable.issubset(configured):
            raise ValueError("selectable models must be configured")

        self._default_alias = default_alias
        self._configured_aliases = configured
        self._selectable_aliases = selectable
        self._repository = repository or ConfigModelFile(
            get_plugin_data_file("state.json"),
            _ActiveModelState,
            default=lambda: _ActiveModelState(active_model=default_alias),
        )
        self._lock = Lock()

    async def snapshot(self) -> _ActiveModelState:
        """Return the active model, repairing corrupt or stale state."""
        async with self._lock:
            try:
                state = self._repository.load()
            except DecodeError, OSError, ValidationError:
                logger.warning("LLM active model state is corrupt; resetting it.")
                return self._repair()

            if state.active_model not in self._selectable_aliases:
                logger.warning(
                    "LLM active model is no longer selectable; resetting it."
                )
                return self._repair()
            return state

    async def select(self, alias: str) -> _ActiveModelState:
        """Persist one globally selectable model alias."""
        alias = alias.strip()
        if alias not in self._configured_aliases:
            raise LLMModelSelectionError("Unknown model alias.")
        if alias not in self._selectable_aliases:
            raise LLMModelSelectionError("The model alias is not selectable.")

        state = _ActiveModelState(active_model=alias)
        async with self._lock:
            self._repository.save(state)
        return state

    def _repair(self) -> _ActiveModelState:
        state = _ActiveModelState(active_model=self._default_alias)
        self._repository.save(state)
        return state


__all__ = ["ActiveModelStore"]
