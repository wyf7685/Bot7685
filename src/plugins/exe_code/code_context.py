import contextlib
from asyncio import Future
from collections import defaultdict
from copy import deepcopy
from typing import Callable, Coroutine, Dict, List

from nonebot.adapters import Bot, Event, Message
from nonebot.log import logger

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


class ContextManager:
    contexts: Dict[str, T_Context]
    locked: Dict[str, bool]
    waitlist: Dict[str, List[Future[None]]]

    def __init__(self):
        self.contexts = defaultdict(lambda: deepcopy(default_context))
        self.locked = defaultdict(lambda: False)
        self.waitlist = defaultdict(list)

    def get_context(self, uin: str) -> T_Context:
        return self.contexts[uin]

    def _solve_code(
        self, uin: str, code: str
    ) -> Callable[[], Coroutine[None, None, None]]:
        ctx = self.get_context(uin)

        # 预处理代码
        func_name = "__executor__"
        global_prefix = ("global " + ",".join(list(ctx)) + "\n    ") if ctx else ""
        lines = [global_prefix] + code.split("\n")
        func_code = ("\n" + EXECUTOR_FUNCTION_INDENT).join(lines)

        # 包装为异步函数
        exec(EXECUTOR_FUNCTION % (func_name, func_code), ctx)

        return ctx.pop(func_name)

    async def execute(self, event: Event, bot: Bot, code: str):
        # 根据user_id获取ctx
        uin = event.get_user_id()
        ctx = self.get_context(uin)

        async with self.lock_context(uin):
            # 预处理ctx
            ctx.update(load_const(uin))

            # 执行代码
            api = API(event, bot, ctx)
            await self._solve_code(uin, code)()
            if buf := Buffer(uin).getvalue().rstrip("\n"):
                await api.feedback(buf)

        # 处理异常
        if (exc := ctx.get("__exception__", (None, None)))[0]:
            raise exc[0]  # type: ignore

    def set_gev(self, event: Event) -> None:
        ctx = self.get_context(event.get_user_id())
        ctx["gev"] = event

    def set_gem(self, event: Event, msg: Message) -> None:
        ctx = self.get_context(event.get_user_id())
        ctx["gem"] = msg

    @contextlib.asynccontextmanager
    async def lock_context(self, uin: str):
        if self.locked[uin]:
            fut = Future()
            self.waitlist[uin].append(fut)
            await fut
        self.locked[uin] = True

        try:
            yield
        finally:
            if self.waitlist[uin]:
                self.waitlist[uin].pop(0).set_result(None)
            self.locked[uin] = False
