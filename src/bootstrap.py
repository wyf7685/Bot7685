import importlib
import logging
import pathlib
import time
from typing import Any, cast

import nonebot
import yaml
from nonebot.adapters import Adapter
from nonebot.internal.driver import ASGIMixin


def setup_logger() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    nonebot.logger.add(
        "./logs/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        format=(
            "<g>{time:HH:mm:ss}</g> "
            "[<lvl>{level}</lvl>] "
            "<c><u>{name}</u></c> | "
            "<c>{function}:{line}</c> | "
            "{message}"
        ),
    )
    nonebot.logger.add(
        "./logs/{time:YYYY-MM-DD}.colorize.log",
        rotation="00:00",
        level="DEBUG",
        colorize=True,
        diagnose=True,
        format=(
            "<g>{time:HH:mm:ss}</g> "
            "[<lvl>{level}</lvl>] "
            "<c><u>{name}</u></c> | "
            "<c>{function}:{line}</c> | "
            "{message}"
        ),
    )


def _load_yaml(file_path: pathlib.Path) -> dict[str, Any]:
    with file_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> dict[str, Any]:
    config_dir = pathlib.Path("config")
    root_config = config_dir / "config.yaml"
    if not root_config.exists():
        return {}

    config: dict[str, Any] = _load_yaml(root_config)

    env = str(config.get("environment", "prod"))
    env_config = config_dir / f"{env}.yaml"
    if not env_config.exists():
        return config

    config |= _load_yaml(env_config)

    env_dir = config_dir / env
    if not env_dir.exists():
        return config

    for p in env_dir.iterdir():
        if p.suffix == ".yaml":
            config |= _load_yaml(p)

    return config


def load_adapters(adapters: list[str]) -> None:
    driver = nonebot.get_driver()
    logger = nonebot.logger.opt(colors=True)

    for module_name in adapters:
        logger.debug(f"Loading adapter: <g>{module_name}</g>")
        start = time.time()

        full_name = f"nonebot.adapters.{module_name}"
        try:
            module = importlib.import_module(full_name)
        except ImportError:
            logger.warning(f"Failed to import module: <y>{full_name}</y>")
            continue

        try:
            adapter= cast(type[Adapter], module.Adapter)
        except AttributeError:
            logger.warning(f"Module <y>{full_name}</y> is not a valid adapter")
            continue

        driver.register_adapter(adapter)
        logger.success(
            f"Adapter <g>{adapter.get_name()}</g> loaded"
            f" in <y>{time.time()-start:.3f}</y>s"
        )


def load_plugins(plugins: list[str]) -> None:
    for p in pathlib.Path("src/dev").iterdir():
        if (p.is_dir() and (name := p.name) in plugins) or (
            p.is_file() and p.suffix == ".py" and (name := p.stem) in plugins
        ):
            plugins.remove(name)
            nonebot.logger.opt(colors=True).warning(
                f'Prefer loading plugin <y>{name}</y> from "<m>src.dev.{name}</m>"'
            )

    start = time.time()
    nonebot.load_all_plugins(plugins, ["src/plugins", "src/dev"])
    nonebot.logger.opt(colors=True).success(
        f"Plugins loaded in <y>{time.time()-start:.3f}</y>s"
    )


def init_nonebot() -> ASGIMixin:
    config = load_config()
    adapters = config.pop("adapters", [])
    plugins = config.pop("plugins", [])

    start = time.time()
    setup_logger()
    nonebot.init(**config)
    load_adapters(adapters)
    load_plugins(plugins)
    nonebot.logger.opt(colors=True).success(
        f"NoneBot initialized in <y>{time.time()-start:.3f}</y>s"
    )

    return cast(ASGIMixin, nonebot.get_asgi())
