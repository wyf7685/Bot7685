from __future__ import annotations

from collections.abc import Collection

from anyio import Lock
from msgspec import DecodeError
from nonebot import get_plugin_config, logger
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel, ValidationError

from src.utils import ConfigModelFile

from .config import ZssmConfig
from .contracts import ActiveModelState


class RootConfig(BaseModel):
    zssm: ZssmConfig


def get_zssm_config() -> ZssmConfig:
    """Validate and return the plugin's section of the global configuration."""

    return get_plugin_config(RootConfig).zssm


class ModelSelectionError(ValueError):
    """A safe, user-facing active-model selection error."""


_state_repository = ConfigModelFile(
    get_plugin_data_file("state.json"),
    ActiveModelState,
)


class ActiveModelStore:
    """Linearizable active-model snapshots backed by the plugin data file."""

    def __init__(
        self,
        repository: ConfigModelFile[ActiveModelState] = _state_repository,
    ) -> None:
        self._repository = repository
        self._lock = Lock()

    async def snapshot(
        self,
        config: ZssmConfig,
        configured_models: Collection[str],
    ) -> ActiveModelState:
        """Return a frozen selection snapshot, repairing stale state if necessary."""

        aliases = frozenset(configured_models)
        self._require_valid_default(config, aliases)
        async with self._lock:
            try:
                state = self._repository.load(use_cache=False)
            except DecodeError, OSError, ValidationError:
                logger.warning(
                    "ZSSM active model state is missing or corrupt; resetting it."
                )
                return self._repair(config.default_model)

            if not self._is_selectable(state.active_model, config, aliases):
                logger.warning(
                    "ZSSM active model is no longer selectable; resetting it."
                )
                return self._repair(config.default_model)
            return state

    async def select(
        self,
        alias: str,
        config: ZssmConfig,
        configured_models: Collection[str],
    ) -> ActiveModelState:
        """Persist one selectable alias and return the resulting frozen snapshot."""

        aliases = frozenset(configured_models)
        self._require_valid_default(config, aliases)
        alias = alias.strip()
        if alias == config.vision_model:
            raise ModelSelectionError("The vision model is fallback-only.")
        if alias not in aliases:
            raise ModelSelectionError("Unknown model alias.")
        if alias not in config.selectable_models:
            raise ModelSelectionError("The model alias is not selectable.")

        state = ActiveModelState(active_model=alias)
        async with self._lock:
            self._repository.save(state)
        return state

    def _repair(self, alias: str) -> ActiveModelState:
        state = ActiveModelState(active_model=alias)
        self._repository.save(state)
        return state

    @staticmethod
    def _require_valid_default(
        config: ZssmConfig,
        configured_models: Collection[str],
    ) -> None:
        if config.default_model not in configured_models:
            raise ModelSelectionError("ZSSM model configuration is unavailable.")

    @staticmethod
    def _is_selectable(
        alias: str,
        config: ZssmConfig,
        configured_models: Collection[str],
    ) -> bool:
        return (
            alias != config.vision_model
            and alias in config.selectable_models
            and alias in configured_models
        )


active_model_store = ActiveModelStore()


__all__ = [
    "ActiveModelStore",
    "ModelSelectionError",
    "RootConfig",
    "active_model_store",
    "get_zssm_config",
]
