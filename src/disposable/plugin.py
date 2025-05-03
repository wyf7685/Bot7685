# ruff: noqa: SLF001

import sys
from collections.abc import Callable
from types import ModuleType

import nonebot.plugin
from nonebot.plugin import Plugin, get_plugin_by_module_name
from nonebot.plugin.manager import PluginManager

from .utils import escape_tag, log

type Disposer = Callable[[], object]

_plugin_nodes: dict[str, "PluginNode"] = {}
_internal_dispose: dict[str, set[Disposer]] = {}
_external_dispose: dict[str, set[Disposer]] = {}
_plugins = nonebot.plugin._plugins  # pyright: ignore[reportPrivateUsage]
_managers = nonebot.plugin._managers  # pyright: ignore[reportPrivateUsage]


class PluginNode:
    plugin: Plugin
    dependents: list["PluginNode"]
    dependencies: list["PluginNode"]

    def __init__(self, plugin: Plugin) -> None:
        self.plugin = plugin
        self.dependents = []
        self.dependencies = []

    def _get_disposer(self) -> Disposer:
        disposers: set[Disposer] = {
            *(_external_dispose.get(self.plugin.id_) or set()),
            *(_internal_dispose.get(self.plugin.id_, set())),
        }
        if callable(disposer := getattr(self.plugin.module, "dispose", None)):
            disposers.add(disposer)

        def dispose() -> None:
            for disposer in disposers:
                disposer()

        return dispose

    def dispose(self) -> None:
        if self.plugin.id_ not in _plugin_nodes:
            return

        colored = f'"<y>{escape_tag(self.plugin.id_)}</y>"'
        if self.plugin.id_ != self.plugin.module_name:
            colored = f'{colored} from "<m>{escape_tag(self.plugin.module_name)}</m>"'

        log("TRACE", f"Disposing plugin {colored}")

        for node in self.dependents[:]:
            node.dispose()
            node.dependencies.remove(self)
            self.dependents.remove(node)

        dispose = self._get_disposer()
        assert dispose is not None
        dispose()

        for name in list(sys.modules):
            if name.startswith(self.plugin.module_name):
                del sys.modules[name]

        plugin_id = self.plugin.id_
        _plugins.pop(plugin_id, None)
        _plugin_nodes.pop(plugin_id, None)
        for manager in _managers:
            if plugin_module_name := manager.controlled_modules.get(plugin_id):
                manager.plugins.discard(plugin_module_name)
            for d in manager._third_party_plugin_ids, manager._searched_plugin_ids:  # pyright: ignore[reportPrivateUsage]
                d.pop(plugin_id, None)

        log("TRACE", f"Disposed plugin {colored}")


_original_new_plugin = nonebot.plugin._new_plugin  # pyright: ignore[reportPrivateUsage]
_original_revert_plugin = nonebot.plugin._revert_plugin  # pyright: ignore[reportPrivateUsage]
_original_require = nonebot.plugin.require


def get_current_plugin() -> Plugin | None:
    return nonebot.plugin._current_plugin.get()  # pyright: ignore[reportPrivateUsage]


def _new_plugin(module_name: str, module: ModuleType, manager: PluginManager) -> Plugin:
    plugin = _original_new_plugin(module_name, module, manager)
    plugin_node = PluginNode(plugin)
    _plugin_nodes[plugin.id_] = plugin_node
    if plugin.parent_plugin is not None:
        parent_plugin_node = _plugin_nodes[plugin.parent_plugin.id_]
        plugin_node.dependencies.append(parent_plugin_node)
        parent_plugin_node.dependents.append(plugin_node)
    return plugin


def _revert_plugin(plugin: Plugin) -> None:
    _original_revert_plugin(plugin)
    plugin_node = _plugin_nodes.pop(plugin.id_, None)
    if plugin_node is not None:
        plugin_node.dispose()


def require(name: str) -> ModuleType:
    plugin = get_current_plugin()
    assert plugin is not None

    module = _original_require(name)
    required = get_plugin_by_module_name(name)
    assert required is not None

    node = _plugin_nodes[required.id_]
    current = _plugin_nodes[plugin.id_]
    current.dependencies.append(node)
    node.dependents.append(current)

    return module


def dispose_plugin(plugin_id: str) -> None:
    if (plugin_node := _plugin_nodes.get(plugin_id)) is None:
        raise RuntimeError(f"Plugin {plugin_id} not loaded!")

    plugin_node.dispose()


def dispose_all() -> None:
    while _plugin_nodes:
        node = next(iter(_plugin_nodes.values()))
        while node.dependencies:
            node = node.dependencies[0]
        node.dispose()


def internal_dispose(plugin_id: str, func: Disposer) -> None:
    disposers = _internal_dispose.setdefault(
        plugin_id, {lambda: _internal_dispose.pop(plugin_id, None)}
    )
    disposers.add(func)


def external_dispose[T: Disposer](plugin_id: str) -> Callable[[T], T]:
    def decorator(func: T) -> T:
        disposers = _external_dispose.setdefault(
            plugin_id, {lambda: _external_dispose.pop(plugin_id, None)}
        )
        disposers.add(func)
        return func

    return decorator


def setup_disposable() -> None:
    import nonebot
    from nonebot import plugin
    from nonebot.plugin import load, manager

    nonebot.require = plugin.require = load.require = require
    plugin._new_plugin = manager._new_plugin = _new_plugin  # pyright: ignore[reportPrivateUsage]
    plugin._revert_plugin = manager._revert_plugin = _revert_plugin  # pyright: ignore[reportPrivateUsage]
