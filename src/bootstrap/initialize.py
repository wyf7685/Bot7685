import functools
import logging
import time
from collections.abc import Callable

import nonebot
from bot7685_ext.nonebot import mount_plugin_loader_hook, register_htmlrender_patch
from nonebot.adapters import Adapter
from nonebot.utils import resolve_dot_notation

from src.utils import logger_wrapper

from .config import BootstrapConfig, LogLevelMap, load_config
from .logo import print_logo
from .patch_lifespan import patch_driver_lifespan, patch_require

log = logger_wrapper("Bootstrap")


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
        colorize=True,
        diagnose=True,
        format=log_format,
    )


def _timer[**P, R](info: str, /) -> Callable[[Callable[P, R]], Callable[P, R]]:
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.time()
            result = func(*args, **kwargs)
            elapsed = time.time() - start
            log("DEBUG", f"{info} took <y>{elapsed:.3f}</y>s")
            return result

        return wrapper

    return decorator


def load_adapter(module_name: str) -> type[Adapter] | None:
    try:
        return resolve_dot_notation(module_name, "Adapter", "nonebot.adapters.")
    except ImportError, AttributeError:
        log("WARNING", f"Failed to resolve adapter: <y>{module_name}</y>")
        return None


@_timer("Loading adapters")
def load_adapters(config: BootstrapConfig) -> None:
    driver = nonebot.get_driver()
    for module_name in config.adapters:
        message = f"Loading adapter: <m>{module_name}</m>"
        log("DEBUG", message)
        if adapter := _timer(message)(load_adapter)(module_name):
            driver.register_adapter(adapter)
            log(
                "SUCCESS",
                f"Succeeded to load adapter <g>{adapter.get_name()}</g>"
                f' from "<m>{module_name}</m>"',
            )


@_timer("Loading plugins")
def load_plugins(config: BootstrapConfig) -> None:
    nonebot.load_all_plugins(
        module_path=config.plugins,
        plugin_dir={config.plugin_dirs}
        if isinstance(config.plugin_dirs, str)
        else (config.plugin_dirs or set()),
    )


@_timer("Initializing NoneBot")
def init_nonebot() -> object:
    config = load_config()
    bootstrap_config = BootstrapConfig.from_config(config)

    setup_logger(bootstrap_config.logging_override)
    mount_plugin_loader_hook()
    register_htmlrender_patch()
    patch_require()
    config.pop("_env_file", None)
    nonebot.init(_env_file=None, **config)
    driver = nonebot.get_driver()
    patch_driver_lifespan(driver)
    print_logo(lambda line: log("SUCCESS", line), mode="rich")
    load_adapters(bootstrap_config)
    load_plugins(bootstrap_config)

    return nonebot.get_app()
