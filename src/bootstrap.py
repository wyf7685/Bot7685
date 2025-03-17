import importlib
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import nonebot
from msgspec import yaml as msgyaml
from nonebot.utils import deep_update, logger_wrapper
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from nonebot.adapters import Adapter

log = logger_wrapper("Bootstrap")


class Config(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    adapters: set[str] = set()
    plugins: set[str] = set()
    plugin_dir: str = "src/plugins"
    dev_plugin_dir: str = "src/dev"
    preload_plugins: set[str] = set()


def setup_logger() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
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


def _load_yaml(file_path: Path) -> dict[str, Any]:
    return msgyaml.decode(file_path.read_bytes()) or {}


def load_config() -> dict[str, Any]:
    config_dir = Path("config")
    root_config = config_dir / "config.yaml"
    if not root_config.exists():
        return {}

    config = _load_yaml(root_config)

    env = str(config.get("environment", "prod"))
    env_config = config_dir / f"{env}.yaml"
    if not env_config.exists():
        return config

    config = deep_update(config, _load_yaml(env_config))

    env_dir = config_dir / env
    if not env_dir.exists():
        return config

    for p in env_dir.iterdir():
        if p.suffix == ".yaml":
            config = deep_update(config, _load_yaml(p))

    return config


def load_adapters(config: Config) -> None:
    driver = nonebot.get_driver()

    for module_name in config.adapters:
        log("DEBUG", f"Loading adapter: <g>{module_name}</g>")
        start = time.time()

        full_name = f"nonebot.adapters.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError:
            log("WARNING", f"Failed to import module: <y>{full_name}</y>")
            continue

        try:
            adapter: type[Adapter] = module.Adapter
        except AttributeError:
            log("WARNING", f"Module <y>{full_name}</y> is not a valid adapter")
            continue

        driver.register_adapter(adapter)
        log(
            "SUCCESS",
            f"Adapter <g>{adapter.get_name()}</g> loaded "
            f"in <y>{time.time() - start:.3f}</y>s",
        )


def load_plugins(config: Config) -> None:
    plugin_dirs: list[str] = []

    if (plugin_dir := config.plugin_dir) and Path(plugin_dir).is_dir():
        plugin_dirs.append(plugin_dir)

    if (dev_dir := config.dev_plugin_dir) and Path(dev_dir).is_dir():
        plugin_dirs.append(dev_dir)
        for p in Path(dev_dir).iterdir():
            if (p.is_dir() and (name := p.name) in config.plugins) or (
                p.is_file() and p.suffix == ".py" and (name := p.stem) in config.plugins
            ):
                config.plugins.discard(name)
                log(
                    "WARNING",
                    f'Prefer loading plugin <y>{name}</y> from "<m>src.dev.{name}</m>"',
                )

    start = time.time()
    nonebot.load_all_plugins(config.preload_plugins, [])
    nonebot.load_all_plugins(config.plugins, plugin_dirs)
    log("SUCCESS", f"Plugins loaded in <y>{time.time() - start:.3f}</y>s")


def init_nonebot() -> Any:
    config = Config.model_validate(load_config())

    start = time.time()
    setup_logger()
    nonebot.init(**config.model_dump())
    load_adapters(config)
    load_plugins(config)
    log("SUCCESS", f"NoneBot initialized in <y>{time.time() - start:.3f}</y>s")

    return nonebot.get_app()
