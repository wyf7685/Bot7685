import contextlib
from asyncio import Future
from copy import deepcopy
from queue import Queue
from typing import Any, Awaitable, Callable, ClassVar, Self, cast

from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger
from nonebot_plugin_alconna.uniseg import Image, UniMessage
from nonebot_plugin_session import Session

from .constant import T_Context
from .interface import API, Buffer, default_context

logger = logger.opt(colors=True)

EXECUTOR_INDENT = " " * 8
EXECUTOR_FUNCTION = """\
last_exc, __exception__ = __exception__,  (None, None)
async def __executor__():
    try:
        %s
    except BaseException as e:
        global __exception__
        __exception__ = (e, __import__("traceback").format_exc())
    finally:
        globals().update({
            k: v for k, v in dict(locals()).items()
            if not k.startswith("__") and not k.endswith("__")
        })
"""


class Context:
    _contexts: ClassVar[dict[str, Self]] = {}

    uin: str
    ctx: T_Context
    locked: bool
    waitlist: Queue[Future[None]]

    def __init__(self, uin: str) -> None:
        self.uin = uin
        self.ctx = deepcopy(default_context)
        self.locked = False
        self.waitlist = Queue()

    @classmethod
    def get_context(cls, session: Session) -> Self:
        if (uin := session.id1 or "") not in cls._contexts:
            cls._contexts[uin] = cls(uin)

        return cls._contexts[uin]

    @contextlib.asynccontextmanager
    async def _lock(self):
        if self.locked:
            fut = Future()
            self.waitlist.put(fut)
            await fut
        self.locked = True

        try:
            yield
        finally:
            if not self.waitlist.empty():
                self.waitlist.get().set_result(None)
            self.locked = False

    def solve_code(self, code: str) -> Callable[[], Awaitable[None]]:
        # 预处理代码
        lines = []
        if self.ctx:
            lines.append("global " + ",".join(list(self.ctx)) + "\n    ")
        lines.extend(code.split("\n"))
        func_code = ("\n" + EXECUTOR_INDENT).join(lines)

        # 包装为异步函数
        exec(EXECUTOR_FUNCTION % (func_code,), self.ctx)
        return self.ctx.pop("__executor__")

    @classmethod
    async def execute(cls, session: Session, bot: Bot, code: str) -> None:
        self = cls.get_context(session)
        async with self._lock():
            API(bot, session, self.ctx).export_to(self.ctx)
            await self.solve_code(code)()
            if buf := Buffer(self.uin).getvalue().rstrip("\n"):
                await UniMessage(buf).send()

        # 处理异常
        if (exc := self.ctx.get("__exception__", (None, None)))[0]:
            raise cast(Exception, exc[0])

    def set_value(self, varname: str, value: Any) -> None:
        self.ctx[varname] = value

    def set_gev(self, event: Event) -> None:
        self.set_value("gev", event)

    def set_gem(self, msg: Message) -> None:
        self.set_value("gem", msg)

    def set_gurl(self, msg: UniMessage | Image) -> None:
        url = ""
        if isinstance(msg, UniMessage) and msg.has(Image):
            url = msg[Image, 0].url
        elif isinstance(msg, Image):
            url = msg.url
        self.set_value("gurl", url)

    def __getitem__(self, key: str) -> Any:
        return self.ctx[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.ctx[key] = value
