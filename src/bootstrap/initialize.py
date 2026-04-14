import functools
import logging
import time
from collections.abc import Callable
from typing import Any, override

import nonebot
from bot7685_ext.nonebot import mount_plugin_loader_hook, register_htmlrender_patch
from nonebot import _log_patcher, _resolve_combine_expr
from nonebot.adapters import Adapter
from nonebot.compat import model_dump
from nonebot.config import Config, Env
from nonebot.drivers import Driver
from nonebot.utils import escape_tag, resolve_dot_notation

from src.utils import Decorator, logger_wrapper

from .config import BootstrapConfig, LogLevelMap, load_config
from .logo import print_logo
from .patch_lifespan import ExtendedLifespan, patch_require

log = logger_wrapper("Bootstrap")


def setup_logger(logging_override: LogLevelMap | None = None) -> None:
    if logging_override is not None:
        for name, level in logging_override.items():
            logging.getLogger(name).setLevel(level)

    nonebot.logger.configure(patcher=_log_patcher)

    log_format = (
        "<g>{time:HH:mm:ss}</g> [<lvl>{level}</lvl>] <c><u>{name}</u></c> | {message}"
    )
    nonebot.logger.add(
        "./logs/{time:YYYY-MM-DD}.log",
        rotation="00:00",
        level="DEBUG",
        colorize=True,
        diagnose=True,
        format=log_format,
    )


def timer[**P, R](info: str, /) -> Decorator[P, R]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            log.debug(f"{info} took <y>{elapsed:.3f}</y>s")
            return result

        return wrapper

    return decorator


def _create_driver_class(combine_expr: str) -> type[Driver]:
    class Driver(_resolve_combine_expr(combine_expr)):
        @override
        def __init__(self, env: Env, config: Config) -> None:
            super().__init__(env, config)
            self._lifespan = ExtendedLifespan()

    return Driver


def create_driver(config_dict: dict[str, Any]) -> Driver:
    log.success("NoneBot is initializing...")
    env = Env(environment=config_dict.get("environment", "prod"))
    config = Config(**config_dict)

    nonebot.logger.configure(extra={"nonebot_log_level": config.log_level})
    log.info(f"Current <y><b>Env: {escape_tag(env.environment)}</b></y>")
    log.debug(f"Loaded <y><b>Config</b></y>: {escape_tag(str(model_dump(config)))}")

    driver = _create_driver_class(config.driver)(env, config)
    nonebot._driver = driver  # noqa: SLF001
    return driver


def load_adapter(module_name: str) -> type[Adapter] | None:
    try:
        return resolve_dot_notation(module_name, "Adapter", "nonebot.adapters.")
    except ImportError, AttributeError:
        log.warning(f"Failed to resolve adapter: <y>{module_name}</y>")
        return None


@timer("Loading adapters")
def load_adapters(config: BootstrapConfig) -> None:
    driver = nonebot.get_driver()
    for module_name in config.adapters:
        message = f"Loading adapter: <m>{module_name}</m>"
        log.debug(message)
        if adapter := timer(message)(load_adapter)(module_name):
            driver.register_adapter(adapter)
            log.success(
                f"Succeeded to load adapter <g>{adapter.get_name()}</g>"
                f' from "<m>{module_name}</m>"',
            )


@timer("Loading plugins")
def load_plugins(config: BootstrapConfig) -> None:
    nonebot.load_all_plugins(
        module_path=config.plugins,
        plugin_dir={config.plugin_dirs}
        if isinstance(config.plugin_dirs, str)
        else (config.plugin_dirs or set()),
    )


@timer("Initializing NoneBot")
def init_nonebot() -> object:
    config = load_config()
    bootstrap_config = BootstrapConfig.from_config(config)

    setup_logger(bootstrap_config.logging_override)
    mount_plugin_loader_hook()
    register_htmlrender_patch()
    patch_require()
    create_driver(config)
    print_logo(log.success, mode="rich")
    load_adapters(bootstrap_config)
    load_plugins(bootstrap_config)

    return nonebot.get_app()
