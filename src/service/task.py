from collections.abc import Awaitable, Callable
from typing import cast

import anyio
import nonebot
from nonebot.plugin import PluginMetadata
from nonebot.utils import escape_tag, is_coroutine_callable, run_sync

from src.utils import caller_loc_repr

__plugin_meta__ = PluginMetadata(
    name="Tasks",
    description="提供任务调度工具",
    usage="call_later(delay, call) / call_soon(call)",
    type="library",
)

driver = nonebot.get_driver()


def call_later[**P](
    delay: float,
    call: Callable[P, object],
    /,
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    if not is_coroutine_callable(call):
        call = run_sync(call)
    call = cast("Callable[P, Awaitable[object]]", call)
    loc = caller_loc_repr()

    async def task() -> None:
        await anyio.sleep(max(0, delay))

        try:
            await call(*arg, **kwargs)
        except Exception:
            nonebot.logger.opt(colors=True).exception(
                f"Uncaught exception when calling <y>{escape_tag(repr(call))}</>"
                f" (from <c>{escape_tag(loc)}</>):"
            )

    driver.task_group.start_soon(task, name=f"Scheduled Task from {loc}")


def call_soon[**P](
    call: Callable[P, object],
    /,
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    call_later(0, call, *arg, **kwargs)
