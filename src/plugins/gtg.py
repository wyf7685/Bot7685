from collections.abc import Awaitable, Callable

import anyio
import anyio.abc
import nonebot
import nonebot.plugin

__plugin_meta__ = nonebot.plugin.PluginMetadata(
    name="GlobalTaskGroup",
    description="提供全局任务组",
    usage="call_later(delay, call) / call_soon(call)",
    type="library",
)

driver = nonebot.get_driver()


def call_later[**P](
    delay: float,
    call: Callable[P, Awaitable[object]],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    async def wrapper() -> None:
        await anyio.sleep(max(0, delay))

        try:
            await call(*arg, **kwargs)
        except Exception:
            nonebot.logger.exception(f"Uncaught exception when calling {call}")

    driver.task_group.start_soon(wrapper)


def call_soon[**P](
    call: Callable[P, Awaitable[object]],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    call_later(0, call, *arg, **kwargs)
