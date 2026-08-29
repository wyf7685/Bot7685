import os
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from nonebot.utils import deep_update
from pydantic import BaseModel

from src.utils import logger_wrapper

type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
type LogLevelMap = dict[str, LogLevel]

log = logger_wrapper("Bootstrap::Config")
_decoders: dict[str, Callable[[bytes], dict[str, object]]] = {}
CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


def _find_config_file(fp: Path) -> Path | None:
    for suffix in ".toml", ".yaml", ".yml", ".json":
        if (file := fp.with_suffix(suffix)).exists():
            return file
    return None


def _get_decoder(suffix: str) -> Callable[[bytes], dict[str, object]] | None:
    if suffix not in _decoders:
        match suffix:
            case ".toml":
                from msgspec import toml as module
            case ".yaml" | ".yml":
                from msgspec import yaml as module
            case ".json":
                from msgspec import json as module
            case _:
                return None
        _decoders[suffix] = module.decode

    return _decoders[suffix]


def _load_file(fp: Path) -> dict[str, object]:
    if (decoder := _get_decoder(fp.suffix)) is None:
        log.warning(f"Unsupported configuration file type: <y>{fp.suffix}</y>")
        return {}

    data: dict[str, object] = decoder(fp.read_bytes()) or {}

    if data.pop("scope_compat", None):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                del data[key]
                for k, v in value.items():
                    data[f"{key}_{k}"] = v

    return data


def load_config(config_dir: Path = CONFIG_DIR) -> dict[str, object]:
    if (root_config := _find_config_file(config_dir / "config")) is None:
        log.warning("No configuration file found in <y>config/</y> directory")
        return {}

    config = _load_file(root_config)
    env = os.getenv("ENVIRONMENT") or str(config.get("environment", "prod"))
    config["environment"] = env

    if not (env_dir := config_dir / env).exists():
        log.warning(f"No environment configuration directory found for <y>{env}</y>")
        return config
    if not (env_config := _find_config_file(env_dir / "config")):
        log.warning(f"No environment configuration file found for <y>{env}</y>")
        return config

    config = deep_update(config, _load_file(env_config))
    for p in sorted(env_dir.iterdir()):
        if p.is_file() and p != env_config:
            config = deep_update(config, _load_file(p))

    return config


class BootstrapConfig(BaseModel):
    adapters: set[str] = set()
    plugins: set[str] = set()
    plugin_dirs: str | set[str] | None = "src/plugins"
    logging_override: LogLevelMap | None = None

    @classmethod
    def from_config(cls, config: dict[str, object]) -> BootstrapConfig:
        return cls.model_validate(config.pop("bootstrap", {}))
