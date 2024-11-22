import typing as _t

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

__global_task_group: anyio.abc.TaskGroup | None = None


@nonebot.get_driver().on_startup
async def _() -> None:
    global __global_task_group
    __global_task_group = anyio.create_task_group()
    await __global_task_group.__aenter__()


@nonebot.get_driver().on_shutdown
async def _() -> None:
    global __global_task_group
    if __global_task_group is not None:
        __global_task_group.cancel_scope.cancel()
        await __global_task_group.__aexit__(None, None, None)


def call_later[**P](
    delay: float,
    call: _t.Callable[P, _t.Awaitable[_t.Any]],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    if __global_task_group is None:
        raise RuntimeError("Task group not initialized")

    async def wrapper() -> None:
        if delay > 0:
            await anyio.sleep(delay)

        try:
            await call(*arg, **kwargs)
        except Exception as err:
            nonebot.logger.opt(exception=err).error(
                f"Uncaught exception when calling {call}"
            )

    __global_task_group.start_soon(wrapper)


def call_soon[**P](
    call: _t.Callable[P, _t.Awaitable[_t.Any]],
    *arg: P.args,
    **kwargs: P.kwargs,
) -> None:
    call_later(0, call, *arg, **kwargs)
