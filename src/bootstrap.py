import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import nonebot
from msgspec import toml as msgtoml
from msgspec import yaml as msgyaml
from nonebot.compat import type_validate_python
from nonebot.utils import deep_update, logger_wrapper, resolve_dot_notation
from pydantic import BaseModel

from .logo import print_logo
from .utils import find_and_link_external

if TYPE_CHECKING:
    from collections.abc import Callable

    from nonebot.adapters import Adapter

log = logger_wrapper("Bootstrap")
type LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
type LogLevelMap = dict[str, LogLevel]


class Config(BaseModel):
    adapters: set[str] = set()
    plugins: set[str] = set()
    plugin_dirs: str | set[str] | None = "src/plugins"
    logging_override: LogLevelMap | None = None


def setup_logger(logging_override: LogLevelMap | None = None) -> None:
    if logging_override is not None:
        for name, level in logging_override.items():
            logging.getLogger(name).setLevel(level)

    log_format = (
        "<g>{time:HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}"
    )
    nonebot.logger.add(
        "./logs/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        format=log_format,
    )
    nonebot.logger.add(
        "./logs/color/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        colorize=True,
        diagnose=True,
        format=log_format,
    )


def _find_config_file(fp: Path) -> Path | None:
    for suffix in ".toml", ".yaml", ".yml":
        if (file := fp.with_suffix(suffix)).exists():
            return file
    return None


def _load_file(fp: Path) -> dict[str, object]:
    match fp.suffix:
        case ".toml":
            decoder = msgtoml.decode
        case ".yaml" | ".yml":
            decoder = msgyaml.decode
        case x:
            log("WARNING", f"Unsupported configuration file type: <y>{x}</y>")
            return {}

    data: dict[str, object] = decoder(fp.read_bytes()) or {}

    if data.pop("scope_compat", None):
        for key, value in list(data.items()):
            if isinstance(value, dict):
                del data[key]
                for k, v in value.items():
                    data[f"{key}_{k}"] = v

    return data


def load_config() -> dict[str, object]:
    config_dir = Path("config")
    if (root_config := _find_config_file(config_dir / "config")) is None:
        log("WARNING", "No configuration file found in <y>config/</y> directory")
        return {}

    config = _load_file(root_config)

    env = str(config.get("environment", "prod"))
    if (env_config := _find_config_file(config_dir / env)) is None:
        log("WARNING", f"No environment configuration file found for <y>{env}</y>")
        return config

    config = deep_update(config, _load_file(env_config))

    if (env_dir := config_dir / env).exists():
        for p in filter(Path.is_file, env_dir.iterdir()):
            config = deep_update(config, _load_file(p))
    else:
        log("WARNING", f"No environment directory found for <y>{env}</y>")

    return config


def _perf[**P, R](info: str) -> "Callable[[Callable[P, R]], Callable[P, R]]":
    def decorator(func: "Callable[P, R]") -> "Callable[P, R]":
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            log("DEBUG", f"{info} took <y>{elapsed:.3f}</y>s")
            return result

        return wrapper

    return decorator


def load_adapter(module_name: str) -> type["Adapter"] | None:
    try:
        return resolve_dot_notation(module_name, "Adapter", "nonebot.adapters.")
    except (ImportError, AttributeError):
        log("WARNING", f"Failed to resolve adapter: <y>{module_name}</y>")
        return None


@_perf("Loading adapters")
def load_adapters(config: Config) -> None:
    driver = nonebot.get_driver()
    for module_name in config.adapters:
        log("DEBUG", f"Loading adapter: <g>{module_name}</g>")
        load = _perf(f"Loading adapter <g>{module_name}</g>")(load_adapter)
        if adapter := load(module_name):
            driver.register_adapter(adapter)
            log("SUCCESS", f"Adapter <g>{adapter.get_name()}</g> loaded successfully")


@_perf("Loading plugins")
def load_plugins(config: Config) -> None:
    nonebot.load_all_plugins(
        module_path=config.plugins,
        plugin_dir={config.plugin_dirs}
        if isinstance(config.plugin_dirs, str)
        else (config.plugin_dirs or set()),
    )


@_perf("Initializing NoneBot")
def init_nonebot() -> object:
    config = load_config()
    config.pop("_env_file", None)
    bootstrap_config = type_validate_python(Config, config.pop("bootstrap", {}))

    setup_logger(bootstrap_config.logging_override)
    nonebot.init(_env_file=None, **config)
    print_logo(lambda line: log("SUCCESS", line))
    find_and_link_external()
    load_adapters(bootstrap_config)
    load_plugins(bootstrap_config)

    return nonebot.get_app()
