import contextlib
import functools
import importlib
import inspect
from collections import defaultdict
from collections.abc import Sequence
from itertools import pairwise
from types import ModuleType, TracebackType
from typing import Any, override

import anyio
from nonebot.internal.driver import Driver
from nonebot.internal.driver._lifespan import LIFESPAN_FUNC, Lifespan
from nonebot.plugin import Plugin
from nonebot.plugin import _current_plugin as current_plugin
from nonebot.plugin import require as original_require
from nonebot.utils import escape_tag, run_sync

from src.utils import logger_wrapper

HOOK_PLUGIN_ID_ATTR = "__bot7685_hook_plugin_id__"


def _attach_plugin_id(func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def wrapper_async() -> Any:
            return await func()

        wrapper = wrapper_async
    else:

        @functools.wraps(func)
        def wrapper_sync() -> Any:
            return func()

        wrapper = wrapper_sync

    plugin = current_plugin.get()
    plugin_id = plugin.id_ if plugin else None

    # nonebot_plugin_alconna.matcher:AlconnaMatcher._run_tests
    if (
        func.__module__ == "nonebot_plugin_alconna.matcher"
        and func.__qualname__ == "AlconnaMatcher._run_tests"
    ):

        @functools.wraps(func)
        async def _wrapper() -> Any:
            return func()

        wrapper = _wrapper
        plugin_id = "nonebot_plugin_alconna"

    with contextlib.suppress(Exception):
        setattr(wrapper, HOOK_PLUGIN_ID_ATTR, plugin_id)
    return wrapper


def _debug_print_layers(seq: list[list[LIFESPAN_FUNC]]) -> None:
    for idx, layer in enumerate(seq, 1):
        lifespan_debug(f"Layer {idx}:")
        for func in layer:
            func_name = f"{func.__module__}:{func.__qualname__}"
            plugin_id = getattr(func, HOOK_PLUGIN_ID_ATTR, None) or "unknown"
            lifespan_debug(f"  {escape_tag(func_name)} (from {escape_tag(plugin_id)})")


lifespan_debug = functools.partial(logger_wrapper("Lifespan"), "DEBUG")


class ExtendedLifespan(Lifespan):
    @override
    def on_startup(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        return super().on_startup(_attach_plugin_id(func))

    @override
    def on_ready(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        return super().on_ready(_attach_plugin_id(func))

    @override
    def on_shutdown(self, func: LIFESPAN_FUNC) -> LIFESPAN_FUNC:
        return super().on_shutdown(_attach_plugin_id(func))

    async def _concurrent_run_lifespan_func(
        self, funcs: Sequence[LIFESPAN_FUNC], reverse: bool = False
    ) -> None:
        layers = resolve_hook_execution_sequence(funcs, reverse=reverse)
        _debug_print_layers(layers)
        for layer in layers:
            async with anyio.create_task_group() as tg:
                for func in layer:
                    if inspect.iscoroutinefunction(func):
                        tg.start_soon(func)
                    else:
                        tg.start_soon(run_sync(func))

    @override
    async def startup(self) -> None:
        # create background task group
        self.task_group = anyio.create_task_group()
        await self.task_group.__aenter__()

        # run startup funcs
        if self._startup_funcs:
            lifespan_debug("Running startup hooks...")
            await self._concurrent_run_lifespan_func(self._startup_funcs)

        # run ready funcs
        if self._ready_funcs:
            lifespan_debug("Running ready hooks...")
            await self._concurrent_run_lifespan_func(self._ready_funcs)

    @override
    async def shutdown(
        self,
        *,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if self._shutdown_funcs:
            lifespan_debug("Running shutdown hooks...")
            # reverse shutdown funcs to ensure stack order
            await self._concurrent_run_lifespan_func(self._shutdown_funcs, reverse=True)

        # shutdown background task group
        self.task_group.cancel_scope.cancel()

        with contextlib.suppress(Exception):
            await self.task_group.__aexit__(exc_type, exc_val, exc_tb)

        self._task_group = None


_plugin_deps: dict[str, set[str]] = defaultdict(set)


@functools.wraps(original_require)
def _patched_require(name: str) -> ModuleType:
    module = original_require(name)
    plugin: Plugin | None = getattr(module, "__plugin__", None)
    current = current_plugin.get()
    if plugin and current and plugin.id_ != current.id_:
        _plugin_deps[current.id_].add(plugin.id_)
    return module


def resolve_hook_execution_sequence(
    funcs: Sequence[LIFESPAN_FUNC],
    reverse: bool = False,
) -> list[list[LIFESPAN_FUNC]]:
    if not funcs:
        return []

    plugin_ids: list[str | None] = []
    plugin_func_indices: dict[str, list[int]] = defaultdict(list)

    for index, func in enumerate(funcs):
        plugin_id: str | None = getattr(func, HOOK_PLUGIN_ID_ATTR, None)
        plugin_ids.append(plugin_id)
        if plugin_id is not None:
            plugin_func_indices[plugin_id].append(index)

    in_degree = [0] * len(funcs)
    out_edges: list[set[int]] = [set() for _ in funcs]

    def add_edge(source: int, target: int) -> None:
        if source == target or target in out_edges[source]:
            return
        out_edges[source].add(target)
        in_degree[target] += 1

    first_index = {id: indices[0] for id, indices in plugin_func_indices.items()}
    last_index = {id: indices[-1] for id, indices in plugin_func_indices.items()}
    plugins_in_funcs = set(plugin_func_indices)

    for plugin_id, deps in _plugin_deps.items():
        if plugin_id not in plugins_in_funcs:
            continue

        for dep_id in deps:
            if dep_id not in plugins_in_funcs:
                continue

            if reverse:
                add_edge(last_index[plugin_id], first_index[dep_id])
            else:
                add_edge(last_index[dep_id], first_index[plugin_id])

    # Keep non-plugin hook order deterministic.
    non_plugin_indices = [idx for idx, id in enumerate(plugin_ids) if id is None]
    for source, target in pairwise(non_plugin_indices):
        add_edge(source, target)

    remaining = set(range(len(funcs)))
    ready = [index for index, degree in enumerate(in_degree) if degree == 0]
    layers: list[list[LIFESPAN_FUNC]] = []

    while ready:
        layer_indices = sorted(ready)
        layers.append([funcs[index] for index in layer_indices])

        for index in layer_indices:
            remaining.discard(index)

        next_ready: list[int] = []
        for source in layer_indices:
            for target in out_edges[source]:
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    next_ready.append(target)
        ready = next_ready

    # Fallback for cyclic deps: keep remaining hooks sequential to avoid deadlock.
    if remaining:
        layers.extend([funcs[index]] for index in sorted(remaining))

    return layers


def patch_driver_lifespan(driver: Driver) -> None:
    lifespan = getattr(driver, "_lifespan", None)
    if not isinstance(lifespan, Lifespan):
        raise TypeError("Driver does not have a valid _lifespan attribute")
    lifespan.__class__ = ExtendedLifespan


def patch_require() -> None:
    for name in ("nonebot", "nonebot.plugin", "nonebot.plugin.load"):
        module = importlib.import_module(name)
        setattr(module, "require", _patched_require)  # noqa: B010
