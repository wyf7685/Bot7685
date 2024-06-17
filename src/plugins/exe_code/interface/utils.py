import functools, asyncio
import inspect
from typing import (
    Any,
    Callable,
    ClassVar,
    Coroutine,
    Iterable,
    Optional,
    ParamSpec,
    Protocol,
    Self,
    TypeVar,
    cast,
    overload,
)

from nonebot.adapters import Bot, Event, Message, MessageSegment
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import (
    CustomNode,
    Receipt,
    Reference,
    Segment,
    Target,
    UniMessage,
)

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


def is_super_user(bot: Bot, event: Event) -> bool:
    user_id = event.get_user_id()
    return (
        f"{bot.adapter.get_name().split(maxsplit=1)[0].lower()}:{user_id}"
        in bot.config.superusers
        or user_id in bot.config.superusers
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
    return isinstance(message, (str, Message, MessageSegment, UniMessage, Segment))


async def as_unimsg(message: T_Message) -> UniMessage:
    if isinstance(message, MessageSegment):
        message = cast(type[Message], message.get_message_class())([message])
    if isinstance(message, (str, Segment)):
        message = UniMessage(message)
    elif isinstance(message, Message):
        message = await UniMessage.generate(message=message)

    return message


def rate_limit(count: int):
    class SendMessageFunc(Protocol):
        async def __call__(
            self,
            bot: Bot,
            event: Event,
            target: Optional[Target],
            message: T_Message,
        ) -> Receipt: ...

    class ReachLimit(Exception):
        def __init__(self, msg: str, count: int) -> None:
            self.msg = msg
            self.count = count

    def decorator(call: SendMessageFunc) -> SendMessageFunc:
        call_cnt: dict[str, int] = {}

        def clean_cnt(key: str):
            if key in call_cnt:
                del call_cnt[key]

        @functools.wraps(call)
        async def wrapper(
            bot: Bot,
            event: Event,
            target: Optional[Target],
            message: T_Message,
        ) -> Receipt:
            key = f"{id(bot)}${id(event)}"
            if key not in call_cnt:
                call_cnt[key] = 1
                asyncio.get_event_loop().call_later(60, clean_cnt, key)
            elif call_cnt[key] >= count or call_cnt[key] < 0:
                call_cnt[key] = -1
                raise ReachLimit("消息发送触发次数限制", count)
            else:
                call_cnt[key] += 1

            return await call(
                bot=bot,
                event=event,
                target=target,
                message=message,
            )

        return wrapper

    return decorator


@rate_limit(6)
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
    MessageClass = cast(type[Message], type(event.get_message()))
    MessageSegmentClass = MessageClass.get_segment_class()
    ctx["Message"] = MessageClass
    ctx["MessageSegment"] = MessageSegmentClass
