from importlib import import_module
from typing import Callable, ParamSpec, TypeVar

from nonebot.adapters import Bot, Event

from ..const import INTERFACE_EXPORT_METHOD, T_Context

P = ParamSpec("P")
R = TypeVar("R")


def export(call: Callable[P, R]) -> Callable[P, R]:
    """将一个方法标记为导出函数"""
    setattr(call, INTERFACE_EXPORT_METHOD, True)
    return call


def is_export_method(call: Callable) -> bool:
    return getattr(call, INTERFACE_EXPORT_METHOD, False)


def is_super_user(bot: Bot, event: Event) -> bool:
    user_id = event.get_user_id()
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
        in bot.config.superusers
        or user_id in bot.config.superusers
    )


def export_manager(ctx: T_Context) -> None:
    from ..config import cfg
    from ..code_context import ContextManager

    ctx["ctx_mgr"] = ContextManager
    ctx["get_ctx"] = lambda key: ContextManager.get_context(str(key))
    ctx["set_usr"] = lambda u: (
        s.remove(u) if (u := str(u)) in (s := cfg.user) else s.add(u)
    )
    ctx["set_grp"] = lambda g: (
        s.remove(g) if (g := str(g)) in (s := cfg.group) else s.add(g)
    )
