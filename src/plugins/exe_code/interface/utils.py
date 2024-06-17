import asyncio
import functools
import inspect
from typing import (
    Any,
    Callable,
    ClassVar,
    Coroutine,
    Iterable,
    Optional,
    ParamSpec,
    Self,
    TypeVar,
    cast,
    overload,
)

from nonebot.adapters import Bot, Message, MessageSegment
from nonebot.internal.matcher import current_event
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    Receipt,
    Reference,
    Segment,
    Target,
    UniMessage,
)
from nonebot_plugin_session import Session

from ..constant import (
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


@overload
def debug_log(
    call: Callable[P, Coroutine[None, None, R]]
) -> Callable[P, Coroutine[None, None, R]]: ...


@overload
def debug_log(call: Callable[P, R]) -> Callable[P, R]: ...


def debug_log(
    call: Callable[P, Coroutine[None, None, R] | R]
) -> Callable[P, Coroutine[None, None, R] | R]:
    def log(*args: P.args, **kwargs: P.kwargs):
        logger.debug(f"{call.__name__}: args={args}, kwargs={kwargs}")

    if inspect.iscoroutinefunction(call):
        call = cast(Callable[P, Coroutine[None, None, R]], call)

        @functools.wraps(call, assigned=WRAPPER_ASSIGNMENTS)
        async def wrapper_async(*args: P.args, **kwargs: P.kwargs) -> R:
            log(*args, **kwargs)
            return await call(*args, **kwargs)

        return wrapper_async
    else:
        call = cast(Callable[P, R], call)

        @functools.wraps(call, assigned=WRAPPER_ASSIGNMENTS)
        def wrapper_sync(*args: P.args, **kwargs: P.kwargs) -> R:
            log(*args, **kwargs)
            return call(*args, **kwargs)

        return wrapper_sync


def is_export_method(call: Callable) -> bool:
    return getattr(call, INTERFACE_EXPORT_METHOD, False)


def is_super_user(bot: Bot, uin: str) -> bool:
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{uin}"
        in bot.config.superusers
        or uin in bot.config.superusers
    )


class Buffer:
    _user_buf: ClassVar[dict[str, Self]] = {}
    _buffer: str

    def __new__(cls, uin: str) -> Self:
        if uin not in cls._user_buf:
            buf = super(Buffer, cls).__new__(cls)
            buf._buffer = ""
            cls._user_buf[uin] = buf
        return cls._user_buf[uin]

    def write(self, text: str) -> None:
        assert isinstance(text, str)
        self._buffer += text

    def getvalue(self) -> str:
        value, self._buffer = self._buffer, ""
        return value


class Result:
    error: Optional[Exception] = None
    _data: T_API_Result

    def __init__(self, data: T_API_Result):
        self._data = data
        if isinstance(data, dict):
            self.error = data.get("error")

    def __getitem__(self, key: str | int) -> Any:
        if self._data:
            return self._data.__getitem__(key) # type: ignore

    def __getattribute__(self, name: str) -> Any:
        if isinstance(self._data, dict) and name in self._data:
            return self._data[name]
        return super(Result, self).__getattribute__(name)

    def __repr__(self) -> str:
        if self.error is not None:
            return f"<Result error={self.error!r}>"
        return f"<Result data={self._data!r}>"


def check_message_t(message: Any) -> bool:
    return isinstance(message, (str, Message, MessageSegment, UniMessage, Segment))


async def as_unimsg(message: T_Message) -> UniMessage:
    if isinstance(message, MessageSegment):
        message = cast(type[Message], message.get_message_class())(message)
    if isinstance(message, (str, Segment)):
        message = UniMessage(message)
    elif isinstance(message, Message):
        message = await UniMessage.generate(message=message)

    return message


def _send_message(count: int):
    class ReachLimit(Exception):
        def __init__(self, msg: str, count: int) -> None:
            self.msg = msg
            self.count = count

    call_cnt: dict[str, int] = {}

    def clean_cnt(key: str):
        if key in call_cnt:
            del call_cnt[key]

    async def send_message(
        bot: Bot,
        session: Session,
        target: Optional[Target],
        message: T_Message,
    ) -> Receipt:
        key = f"{id(bot)}${id(session)}"
        if key not in call_cnt:
            call_cnt[key] = 1
            asyncio.get_event_loop().call_later(60, clean_cnt, key)
        elif call_cnt[key] >= count or call_cnt[key] < 0:
            call_cnt[key] = -1
            raise ReachLimit("消息发送触发次数限制", count)
        else:
            call_cnt[key] += 1

        message = await as_unimsg(message)
        return await message.send(target, bot)

    return send_message


send_message = _send_message(6)


async def send_forward_message(
    bot: Bot,
    session: Session,
    target: Optional[Target],
    msgs: Iterable[T_Message],
) -> Receipt:
    return await send_message(
        bot=bot,
        session=session,
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


export_manager = _export_manager()


def export_adapter_message(ctx: T_Context):
    MessageClass = cast(type[Message], type(current_event.get().get_message()))
    MessageSegmentClass = MessageClass.get_segment_class()
    ctx["Message"] = MessageClass
    ctx["MessageSegment"] = MessageSegmentClass
