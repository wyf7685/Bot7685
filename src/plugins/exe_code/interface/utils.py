import functools
import inspect
from typing import Any, Callable, Iterable, Optional, ParamSpec, Type, TypeVar, cast

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_alconna.uniseg import Segment as UniSegment
from nonebot_plugin_alconna.uniseg import Target, UniMessage
from nonebot_plugin_alconna.uniseg.segment import CustomNode, Reference

from ..const import (
    INTERFACE_EXPORT_METHOD,
    INTERFACE_METHOD_DESCRIPTION,
    T_API_Result,
    T_Context,
    T_Message,
)

P = ParamSpec("P")
R = TypeVar("R")

WRAPPER_ASSIGNMENTS = (
    *functools.WRAPPER_ASSIGNMENTS,
    INTERFACE_EXPORT_METHOD,
    INTERFACE_METHOD_DESCRIPTION,
)


def export(call: Callable[P, R]) -> Callable[P, R]:
    """将一个方法标记为导出函数"""
    setattr(call, INTERFACE_EXPORT_METHOD, True)
    return call


def debug_log(call: Callable[P, R]) -> Callable[P, R]:
    def log(*args: P.args, **kwargs: P.kwargs):
        logger.debug(f"{call.__name__}: args={args}, kwargs={kwargs}")

    if inspect.iscoroutinefunction(call):

        @functools.wraps(call, assigned=WRAPPER_ASSIGNMENTS)
        async def wrapper_async(*args: P.args, **kwargs: P.kwargs) -> R:
            log(*args, **kwargs)
            return await call(*args, **kwargs)

        return wrapper_async  # type: ignore
    else:

        @functools.wraps(call, assigned=WRAPPER_ASSIGNMENTS)
        def wrapper_sync(*args: P.args, **kwargs: P.kwargs):
            log(*args, **kwargs)
            return call(*args, **kwargs)

        return wrapper_sync


def is_export_method(call: Callable) -> bool:
    return getattr(call, INTERFACE_EXPORT_METHOD, False)


def is_super_user(bot: Bot, event: Event) -> bool:
    user_id = event.get_user_id()
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
        in bot.config.superusers
        or user_id in bot.config.superusers
    )


class Result:
    error: Optional[Exception] = None
    _data: T_API_Result

    def __init__(self, data: T_API_Result):
        self._data = data
        if isinstance(data, dict) and "error" in data:
            self.error = data["error"]

    def __getitem__(self, key: str | int):
        return self._data.__getitem__(key)  # type: ignore

    def __getattribute__(self, name: str) -> Any:
        if isinstance(self._data, dict) and name in self._data:
            return self._data[name]
        return super(Result, self).__getattribute__(name)

    def __repr__(self) -> str:
        if self.error is not None:
            return f"<Result error={self.error!r}>"
        return f"<Result data={self._data}>"


def check_message_t(message: Any) -> bool:
    return isinstance(message, (str, Message, MessageSegment, UniMessage, UniSegment))


async def as_unimsg(message: T_Message) -> UniMessage:
    if isinstance(message, MessageSegment):
        message = cast(type[Message], message.get_message_class())([message])
    if isinstance(message, (str, UniSegment)):
        message = UniMessage(message)
    elif isinstance(message, Message):
        message = await UniMessage.generate(message=message)

    return message


async def send_message(
    bot: Bot,
    event: Event,
    target: Optional[Target],
    message: T_Message,
) -> Receipt:
    message = await as_unimsg(message)
    return await message.send(target or event, bot)


async def send_forward_message(
    bot: Bot,
    event: Event,
    target: Optional[Target],
    msgs: Iterable[T_Message],
) -> Receipt:
    return await send_message(
        bot=bot,
        event=event,
        target=target,
        message=Reference(
            nodes=[
                CustomNode(
                    uid=bot.self_id,
                    name="forward",
                    content=await as_unimsg(msg),
                )
                for msg in msgs
            ]
        ),
    )


def _export_manager():
    def set_usr(x: Any) -> bool:
        from ..config import cfg

        if (u := str(x)) in cfg.user:
            cfg.user.remove(u)
        else:
            cfg.user.add(u)

        return u in cfg.user

    def set_grp(x: Any) -> bool:
        from ..config import cfg

        if (g := str(x)) in cfg.group:
            cfg.group.remove(g)
        else:
            cfg.group.add(g)

        return g in cfg.group

    def export_manager(ctx: T_Context) -> None:
        from ..code_context import Context

        ctx["get_ctx"] = Context.get_context
        ctx["set_usr"] = set_usr
        ctx["set_grp"] = set_grp

    return export_manager


def export_manager(ctx: T_Context) -> None: ...


export_manager = _export_manager()


def export_adapter_message(ctx: T_Context, event: Event):
    MessageClass: Type[Message[MessageSegment]] = event.get_message().__class__
    MessageSegmentClass = MessageClass.get_segment_class()
    ctx["Message"] = MessageClass
    ctx["MessageSegment"] = MessageSegmentClass
