import contextlib
import functools
import inspect
from collections import Counter, defaultdict
from collections.abc import Awaitable, Callable, Sequence
from itertools import pairwise
from types import TracebackType
from typing import override

import anyio
from nonebot import _resolve_combine_expr
from nonebot.config import Config, Env
from nonebot.drivers import Driver
from nonebot.internal.driver._lifespan import Lifespan
from nonebot.plugin import _current_plugin as current_plugin
from nonebot.utils import escape_tag, run_sync

from src.utils import logger_wrapper

from .require import get_plugin_deps

log = logger_wrapper("Lifespan")

HOOK_PLUGIN_ID_ATTR = "__bot7685_hook_plugin_id__"
type LifespanFunc = Callable[[], object] | Callable[[], Awaitable[object]]

# (module, qualname): plugin_id
KNOWN_HOOKS = {
    ("nonebot_plugin_alconna.matcher", "AlconnaMatcher._run_tests"): "<alconna>",
    ("nonebot.adapters", None): "<nonebot.adapters>",
    ("src.service.cache.impl.adapter", "StatsTracker._do_sync"): "src.service.cache",
}
_HOOK_DISPLAY = "<lk><u>{plugin_id}</></>::<lm>{module}</>:<lg>{qualname}</>"


def _get_func_attr(func: Callable[..., object], attr: str) -> str:
    return getattr(func, attr, None) or "<unknown>"


@functools.cache
def _colorize_hook(func: Callable[..., object]) -> str:
    module = escape_tag(_get_func_attr(func, "__module__"))
    qualname = escape_tag(
        getattr(func, "__qualname__", None)
        or getattr(func, "__name__", None)
        or repr(func)
    )
    plugin_id = escape_tag(_get_func_attr(func, HOOK_PLUGIN_ID_ATTR) or "<unknown>")
    return _HOOK_DISPLAY.format(module=module, qualname=qualname, plugin_id=plugin_id)


@functools.cache
def _colorize_known_hook(mod: str, qual: str) -> str:
    return _HOOK_DISPLAY.format(
        module=escape_tag(mod),
        qualname=escape_tag(qual),
        plugin_id=escape_tag(KNOWN_HOOKS[(mod, qual)]),
    )


def _attach_plugin_id(func: LifespanFunc) -> LifespanFunc:
    plugin = current_plugin.get()
    plugin_id = plugin.id_ if plugin else None

    func_module = _get_func_attr(func, "__module__")
    func_qualname = _get_func_attr(func, "__qualname__")
    for (mod, qual), id in KNOWN_HOOKS.items():
        if func_module.startswith(mod) and (qual is None or func_qualname == qual):
            plugin_id = id
            break

    if inspect.iscoroutinefunction(func):

        async def wrapper() -> object:
            return await func()

    else:

        def wrapper() -> object:
            return func()

    functools.update_wrapper(wrapper, func)
    setattr(wrapper, HOOK_PLUGIN_ID_ATTR, plugin_id)
    return wrapper


def _log_layers(layers: list[list[LifespanFunc]]) -> None:
    for idx, layer in enumerate(layers, 1):
        # 75("─") = 2(" ╘") + 81("═") - 6("Layer ") - 2(" ├")
        log.info(f"<u>Layer <y>{idx}</> </>├" + "─" * (75 - len(str(idx))))
        known_hooks: Counter[tuple[str, str]] = Counter()
        for func in layer:
            func_key = (
                _get_func_attr(func, "__module__"),
                _get_func_attr(func, "__qualname__"),
            )
            if func_key in KNOWN_HOOKS:
                known_hooks[func_key] += 1
            else:
                log.info(f" │ {_colorize_hook(func)}")
        for (mod, qual), count in known_hooks.items():
            log.info(f" │ ...(<le>{count}</>) {_colorize_known_hook(mod, qual)}")
        log.info(" ╘" + "═" * 81)


async def _run_hook(func: LifespanFunc) -> None:
    if not inspect.iscoroutinefunction(func):
        func = run_sync(func)

    timeout_occurred = False

    async def warn_on_timeout() -> None:
        nonlocal timeout_occurred

        delay = 5
        while True:
            await anyio.sleep(delay)
            duration = anyio.current_time() - start
            log.warning(
                f"{_colorize_hook(func)} taking too long to complete "
                f"(<c>{duration:.2f}</>s)"
            )
            timeout_occurred = True
            delay = min(delay * 2, 60)

    async with anyio.create_task_group() as tg:
        tg.start_soon(warn_on_timeout)
        start = anyio.current_time()
        try:
            await func()
        except Exception as exc:
            log.warning(
                f"Uncaught exception in {_colorize_hook(func)}: "
                f"<r>{escape_tag(repr(exc))}</>"
            )
            raise
        finally:
            tg.cancel_scope.cancel()
            duration = anyio.current_time() - start
            (log.warning if timeout_occurred else log.trace)(
                f"{_colorize_hook(func)} completed in <c>{duration:.2f}</>s"
            )


async def _run_hooks(funcs: Sequence[LifespanFunc], reverse: bool = False) -> None:
    layers = resolve_hook_execution_sequence(funcs, reverse=reverse)
    _log_layers(layers)

    for layer in layers:
        async with anyio.create_task_group() as tg:
            for func in layer:
                tg.start_soon(_run_hook, func)


class ExtendedLifespan(Lifespan):
    @override
    def on_startup(self, func: LifespanFunc) -> LifespanFunc:
        return super().on_startup(_attach_plugin_id(func))

    @override
    def on_ready(self, func: LifespanFunc) -> LifespanFunc:
        return super().on_ready(_attach_plugin_id(func))

    @override
    def on_shutdown(self, func: LifespanFunc) -> LifespanFunc:
        return super().on_shutdown(_attach_plugin_id(func))

    @override
    async def startup(self) -> None:
        # create background task group
        self.task_group = anyio.create_task_group()
        await self.task_group.__aenter__()

        # run startup funcs
        if self._startup_funcs:
            log.info("Running <ly>startup</> hooks...")
            await _run_hooks(self._startup_funcs)

        # run ready funcs
        if self._ready_funcs:
            log.info("Running <ly>ready</> hooks...")
            await _run_hooks(self._ready_funcs)

    @override
    async def shutdown(
        self,
        *,
        exc_type: type[BaseException] | None = None,
        exc_val: BaseException | None = None,
        exc_tb: TracebackType | None = None,
    ) -> None:
        if self._shutdown_funcs:
            log.info("Running <ly>shutdown</> hooks...")
            # reverse shutdown funcs to ensure stack order
            await _run_hooks(self._shutdown_funcs, reverse=True)

        # shutdown background task group
        self.task_group.cancel_scope.cancel()

        with contextlib.suppress(Exception):
            await self.task_group.__aexit__(exc_type, exc_val, exc_tb)

        self._task_group = None


def resolve_hook_execution_sequence(
    funcs: Sequence[LifespanFunc],
    reverse: bool = False,
) -> list[list[LifespanFunc]]:
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

    for plugin_id, deps in get_plugin_deps().items():
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
    layers: list[list[LifespanFunc]] = []

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


def create_patched_driver_class(combine_expr: str) -> type[Driver]:
    class Driver(_resolve_combine_expr(combine_expr)):  # ty:ignore[unsupported-base]
        @override
        def __init__(self, env: Env, config: Config) -> None:
            super().__init__(env, config)
            self._lifespan = ExtendedLifespan()

    return Driver
