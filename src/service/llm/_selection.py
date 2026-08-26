from __future__ import annotations

from anyio import Lock
from msgspec import DecodeError
from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.utils import ConfigModelFile

from .config import LLMConfig
from .exceptions import LLMModelSelectionError


class ActiveModelState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    active_model: str = Field(min_length=1)

    @field_validator("active_model")
    @classmethod
    def validate_active_model(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("active_model must not be empty")
        return value


_state_repository = ConfigModelFile(
    get_plugin_data_file("state.json"),
    ActiveModelState,
)


class ActiveModelStore:
    """Process-local active-model state persisted in the LLM service data directory."""

    def __init__(
        self,
        repository: ConfigModelFile[ActiveModelState] = _state_repository,
    ) -> None:
        self._repository = repository
        self._lock = Lock()

    async def snapshot(self, config: LLMConfig) -> ActiveModelState:
        """Return the active model, repairing missing or invalid state."""
        async with self._lock:
            try:
                state = self._repository.load()
            except DecodeError, OSError, ValidationError:
                logger.warning(
                    "LLM active model state is missing or corrupt; resetting it."
                )
                return self._repair(config.default_model)

            if state.active_model not in config.selectable_models:
                logger.warning(
                    "LLM active model is no longer selectable; resetting it."
                )
                return self._repair(config.default_model)
            return state

    async def select(self, alias: str, config: LLMConfig) -> ActiveModelState:
        """Persist one globally selectable model alias."""
        alias = alias.strip()
        if alias not in config.models:
            raise LLMModelSelectionError("Unknown model alias.")
        if alias not in config.selectable_models:
            raise LLMModelSelectionError("The model alias is not selectable.")

        state = ActiveModelState(active_model=alias)
        async with self._lock:
            self._repository.save(state)
        return state

    def _repair(self, alias: str) -> ActiveModelState:
        state = ActiveModelState(active_model=alias)
        self._repository.save(state)
        return state


active_model_store = ActiveModelStore()


__all__ = ["ActiveModelStore", "active_model_store"]
