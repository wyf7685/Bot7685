from typing import TYPE_CHECKING, cast

import anyio
import nonebot
from nonebot.plugin import PluginMetadata
from nonebot.utils import is_coroutine_callable, run_sync

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__plugin_meta__ = PluginMetadata(
    name="GlobalTaskGroup",
    description="提供全局任务组",
    usage="call_later(delay, call) / call_soon(call)",
    type="library",
)

driver = nonebot.get_driver()


def call_later[**P](
    delay: float,
    call: Callable[P, object],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    if not is_coroutine_callable(call):
        call = run_sync(call)
    call = cast("Callable[P, Awaitable[object]]", call)

    async def wrapper() -> None:
        await anyio.sleep(max(0, delay))

        try:
            await call(*arg, **kwargs)
        except Exception:
            nonebot.logger.exception(f"Uncaught exception when calling {call}")

    driver.task_group.start_soon(wrapper)


def call_soon[**P](
    call: Callable[P, object],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    call_later(0, call, *arg, **kwargs)
