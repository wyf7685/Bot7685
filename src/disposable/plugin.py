# ruff: noqa: SLF001

from types import ModuleType

import nonebot.plugin
from nonebot.plugin import Plugin, get_plugin_by_module_name
from nonebot.plugin.manager import PluginManager

from .common import PluginNode, get_current_plugin, plugin_nodes

_original_new_plugin = nonebot.plugin._new_plugin  # pyright: ignore[reportPrivateUsage]
_original_revert_plugin = nonebot.plugin._revert_plugin  # pyright: ignore[reportPrivateUsage]
_original_require = nonebot.plugin.require


def _new_plugin(module_name: str, module: ModuleType, manager: PluginManager) -> Plugin:
    plugin = _original_new_plugin(module_name, module, manager)
    plugin_node = PluginNode(plugin)
    plugin_nodes[plugin.id_] = plugin_node
    if plugin.parent_plugin is not None:
        parent_plugin_node = plugin_nodes[plugin.parent_plugin.id_]
        plugin_node.dependencies.append(parent_plugin_node)
        parent_plugin_node.dependents.append(plugin_node)
    return plugin


def _revert_plugin(plugin: Plugin) -> None:
    _original_revert_plugin(plugin)
    plugin_node = plugin_nodes.pop(plugin.id_, None)
    if plugin_node is not None:
        nonebot.get_driver().task_group.start_soon(plugin_node.dispose)


def require(name: str) -> ModuleType:
    plugin = get_current_plugin()
    assert plugin is not None

    module = _original_require(name)
    required = get_plugin_by_module_name(name)
    assert required is not None

    node = plugin_nodes[required.id_]
    current = plugin_nodes[plugin.id_]
    current.dependencies.append(node)
    node.dependents.append(current)

    return module


def setup_disposable() -> None:
    import nonebot
    from nonebot import plugin
    from nonebot.plugin import load, manager

    nonebot.require = plugin.require = load.require = require
    plugin._new_plugin = manager._new_plugin = _new_plugin  # pyright: ignore[reportPrivateUsage]
    plugin._revert_plugin = manager._revert_plugin = _revert_plugin  # pyright: ignore[reportPrivateUsage]
