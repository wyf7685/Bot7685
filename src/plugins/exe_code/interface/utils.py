from typing import Any, Callable, ParamSpec, Type, TypeVar

from nonebot.adapters import Bot, Event, Message, MessageSegment

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


def _export_manager():
    def set_usr(x: Any) -> None:
        from ..config import cfg

        if (u := str(x)) in cfg.user:
            cfg.user.remove(u)
        else:
            cfg.user.add(u)

    def set_grp(x: Any) -> None:
        from ..config import cfg

        if (g := str(x)) in cfg.group:
            cfg.user.remove(g)
        else:
            cfg.user.add(g)

    def export_manager(ctx: T_Context) -> None:
        from ..code_context import Context

        ctx["get_ctx"] = Context.get_context
        ctx["set_usr"] = set_usr
        ctx["set_grp"] = set_grp

    return export_manager


export_manager = _export_manager()


def export_adapter_message(ctx: T_Context, event: Event):
    MessageClass: Type[Message[MessageSegment]] = event.get_message().__class__
    MessageSegmentClass = MessageClass.get_segment_class()
    ctx["Message"] = MessageClass
    ctx["MessageSegment"] = MessageSegmentClass
