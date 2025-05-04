# ruff: noqa: SLF001

import abc
from typing import Any, override

import nonebot
from nonebot.dependencies import Dependent
from nonebot.internal.driver import Driver
from nonebot.internal.driver._lifespan import LIFESPAN_FUNC
from nonebot.internal.driver.abstract import BOT_HOOK_PARAMS
from nonebot.typing import T_BotConnectionHook, T_BotDisconnectionHook

from .common import get_current_plugin, internal_dispose


class DisposableDriver(Driver, abc.ABC):
    @override
    def on_startup(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        if plugin := get_current_plugin():
            internal_dispose(
                plugin.id_,
                lambda: self._lifespan._startup_funcs.remove(func),  # pyright: ignore[reportPrivateUsage]
            )
        return super().on_startup(func)

    @override
    def on_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        if plugin := get_current_plugin():
            internal_dispose(
                plugin.id_,
                lambda: self._lifespan._shutdown_funcs.remove(func),  # pyright: ignore[reportPrivateUsage]
            )
        return super().on_shutdown(func)

    @override
    @classmethod
    def on_bot_connect(cls, func: T_BotConnectionHook) -> T_BotConnectionHook:
        dependent = Dependent[Any].parse(call=func, allow_types=BOT_HOOK_PARAMS)  # pyright:ignore[reportExplicitAny]
        cls._bot_connection_hook.add(dependent)
        if plugin := get_current_plugin():
            internal_dispose(
                plugin.id_,
                lambda: cls._bot_connection_hook.remove(dependent),
            )
        return func

    @override
    @classmethod
    def on_bot_disconnect(cls, func: T_BotDisconnectionHook) -> T_BotDisconnectionHook:
        dependent = Dependent[Any].parse(call=func, allow_types=BOT_HOOK_PARAMS)  # pyright:ignore[reportExplicitAny]
        cls._bot_disconnection_hook.add(dependent)
        if plugin := get_current_plugin():
            internal_dispose(
                plugin.id_,
                lambda: cls._bot_disconnection_hook.remove(dependent),
            )
        return func


_original_resolve_combine_expr = nonebot._resolve_combine_expr  # pyright: ignore[reportPrivateUsage]


def _resolve_combine_expr(obj_str: str) -> type[Driver]:
    cls = _original_resolve_combine_expr(obj_str)
    return type("CombinedDriver", (DisposableDriver, cls), {})


def setup_disposable() -> None:
    import nonebot

    nonebot._resolve_combine_expr = _resolve_combine_expr  # pyright: ignore[reportPrivateUsage]
