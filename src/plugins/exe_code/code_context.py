import contextlib
from asyncio import Future
from copy import deepcopy
from typing import Any, Awaitable, Callable, Dict, List, ClassVar

from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import UniMessage, Image

from .const import T_Context
from .interface import API
from .user_const_var import default_context, load_const
from .utils import Buffer

logger = logger.opt(colors=True)

EXECUTOR_FUNCTION = """
last_exc = __exception__
__exception__ = (None, None)
async def %s():
    try:
        %s
    except BaseException as e:
        global __exception__
        __exception__ = (e, __import__("traceback").format_exc())
    finally:
        globals().update({
            k: v for k, v in dict(locals()).items()
            if not k.startswith("__")
        })
"""
EXECUTOR_FUNCTION_INDENT = " " * 8


class Context:
    uin: str
    ctx: T_Context
    locked: bool
    waitlist: List[Future[None]]

    def __init__(self, uin: str) -> None:
        self.uin = uin
        self.ctx = deepcopy(default_context)
        self.locked = False
        self.waitlist = []

    @contextlib.asynccontextmanager
    async def _lock(self):
        if self.locked:
            fut = Future()
            self.waitlist.append(fut)
            await fut
        self.locked = True

        try:
            yield
        finally:
            if self.waitlist:
                self.waitlist.pop(0).set_result(None)
            self.locked = False

    def solve_code(self, code: str) -> Callable[[], Awaitable[None]]:
        # 预处理代码
        func_name = "__executor__"
        lines = []
        if self.ctx:
            lines.append("global " + ",".join(list(self.ctx)) + "\n    ")
        lines.extend(code.split("\n"))
        func_code = ("\n" + EXECUTOR_FUNCTION_INDENT).join(lines)

        # 包装为异步函数
        exec(EXECUTOR_FUNCTION % (func_name, func_code), self.ctx)
        return self.ctx.pop(func_name)

    async def execute(self, bot: Bot, event: Event, code: str) -> None:
        async with self._lock():
            # 预处理ctx
            self.ctx.update(load_const(self.uin))

            # 执行代码
            api = API(bot, event, self.ctx)
            await self.solve_code(code)()
            if buf := Buffer(self.uin).getvalue().rstrip("\n"):
                await api.feedback(buf)

        # 处理异常
        if (exc := self.ctx.get("__exception__", (None, None)))[0]:
            raise exc[0]  # type: ignore

    def set_value(self, varname: str, value: Any) -> None:
        self.ctx[varname] = value

    def set_gev(self, event: Event) -> None:
        self.set_value("gev", event)

    def set_gem(self, msg: Message) -> None:
        self.set_value("gem", msg)

    def set_gurl(self, msg: UniMessage) -> None:
        if msg.has(Image):
            self.set_value("gurl", msg[Image, 0].url)

    def __getitem__(self, key: str) -> Any:
        return self.ctx[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.ctx[key] = value


class ContextManager:
    contexts: ClassVar[Dict[str, Context]] = {}

    @classmethod
    def get_context(cls, uin: str | Event) -> Context:
        if isinstance(uin, Event):
            uin = uin.get_user_id()

        if uin not in cls.contexts:
            cls.contexts[uin] = Context(uin)

        return cls.contexts[uin]
