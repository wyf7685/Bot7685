# ruff: noqa: SLF001

import inspect
import sys
from collections.abc import Awaitable, Callable
from typing import cast

import anyio
import nonebot.plugin
from nonebot.plugin import Plugin, get_plugin_by_module_name
from nonebot.utils import run_sync

from .utils import escape_tag, log

type SyncDisposer = Callable[[], object]
type AsyncDisposer = Callable[[], Awaitable[object]]
type AnyDisposer = AsyncDisposer | SyncDisposer

plugin_nodes: dict[str, "PluginNode"] = {}
_internal_dispose: dict[str, set[AnyDisposer]] = {}
_external_dispose: dict[str, set[AnyDisposer]] = {}
plugins = nonebot.plugin._plugins  # pyright: ignore[reportPrivateUsage]
managers = nonebot.plugin._managers  # pyright: ignore[reportPrivateUsage]


class PluginNode:
    plugin: Plugin
    dependents: list["PluginNode"]
    dependencies: list["PluginNode"]

    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.dependents = []
        self.dependencies = []

    @property
    def module_disposer(self) -> AnyDisposer | None:
        return (
            disposer
            if callable(disposer := getattr(self.plugin.module, "dispose", None))
            else None
        )

    @property
    def external_disposer(self) -> set[AnyDisposer]:
        return (_external_dispose.get(self.plugin.id_) or set()).copy()

    @property
    def internal_disposer(self) -> set[AnyDisposer]:
        return (_internal_dispose.get(self.plugin.id_) or set()).copy()

    def get_disposer(self) -> AsyncDisposer:
        disposer = self.module_disposer
        disposers: set[AnyDisposer] = set() if disposer is None else {disposer}
        disposers |= self.external_disposer | self.internal_disposer

        async_disposers: set[AsyncDisposer] = {
            d for d in disposers if inspect.iscoroutinefunction(d)
        }

        if sync_disposers := cast("set[SyncDisposer]", disposers - async_disposers):

            @async_disposers.add
            @run_sync
            def _() -> None:
                for disposer in sync_disposers:
                    disposer()

        async def dispose() -> None:
            async with anyio.create_task_group() as tg:
                for disposer in async_disposers:
                    tg.start_soon(disposer)

        return dispose

    @property
    def disposable(self) -> bool:
        for node in self.dependencies:
            if not node.disposable:
                return False
        return self.module_disposer is not None or bool(self.external_disposer)

    async def dispose(self) -> None:
        if not self.disposable:
            raise RuntimeError(f"Plugin {self.plugin.id_} not disposable!")

        if self.plugin.id_ not in plugin_nodes:
            return

        colored = f'"<y>{escape_tag(self.plugin.id_)}</y>"'
        if self.plugin.id_ != self.plugin.module_name:
            colored += f' from "<m>{escape_tag(self.plugin.module_name)}</m>"'

        log("INFO", f"Disposing plugin {colored}")

        for node in self.dependents[:]:
            await node.dispose()
            node.dependencies.remove(self)
            self.dependents.remove(node)

        dispose = self.get_disposer()
        await dispose()

        for name in list(sys.modules):
            if name.startswith(self.plugin.module_name):
                del sys.modules[name]

        plugin_id = self.plugin.id_
        plugins.pop(plugin_id, None)
        plugin_nodes.pop(plugin_id, None)
        for manager in managers:
            if plugin_module_name := manager.controlled_modules.get(plugin_id):
                manager.plugins.discard(plugin_module_name)
            for d in manager._third_party_plugin_ids, manager._searched_plugin_ids:  # pyright: ignore[reportPrivateUsage]
                d.pop(plugin_id, None)

        log("SUCCESS", f"Disposed plugin {colored}")


def get_current_plugin() -> Plugin | None:
    if plugin := nonebot.plugin._current_plugin.get():  # pyright: ignore[reportPrivateUsage]
        return plugin

    current_frame = inspect.currentframe()
    if current_frame is None:
        return None

    frame = current_frame
    while frame := frame.f_back:
        module_name = (module := inspect.getmodule(frame)) and module.__name__
        if module_name is None:
            return None

        if plugin := get_plugin_by_module_name(module_name):
            return plugin

    return None


async def dispose_plugin(plugin_id: str) -> None:
    if (plugin_node := plugin_nodes.get(plugin_id)) is None:
        raise RuntimeError(f"Plugin {plugin_id} not loaded!")

    await plugin_node.dispose()


async def dispose_all() -> None:
    while plugin_nodes:
        node = next(iter(plugin_nodes.values()))
        while node.dependencies:
            node = node.dependencies[0]
        await node.dispose()


def internal_dispose(plugin_id: str, func: AnyDisposer) -> None:
    disposers = _internal_dispose.setdefault(
        plugin_id, {lambda: _internal_dispose.pop(plugin_id, None)}
    )
    disposers.add(func)


def external_dispose[T: AnyDisposer](plugin_id: str) -> Callable[[T], T]:
    def decorator(func: T) -> T:
        disposers = _external_dispose.setdefault(
            plugin_id, {lambda: _external_dispose.pop(plugin_id, None)}
        )
        disposers.add(func)
        return func

    return decorator
