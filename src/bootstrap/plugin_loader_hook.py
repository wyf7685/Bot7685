from collections.abc import Callable
from importlib.machinery import SourceFileLoader
from types import ModuleType

from nonebot.plugin import Plugin, _current_plugin
from nonebot.plugin.manager import PluginLoader

type BeforePluginLoadHook = Callable[[Plugin], object]
type AfterPluginLoadHook = Callable[[Plugin, Exception | None], object]


_before_plugin_load_hooks: list[BeforePluginLoadHook] = []
_after_plugin_load_hooks: list[AfterPluginLoadHook] = []


def before_plugin_load[F: BeforePluginLoadHook](func: F) -> F:
    _before_plugin_load_hooks.append(func)
    return func


def after_plugin_load[F: AfterPluginLoadHook](func: F) -> F:
    _after_plugin_load_hooks.append(func)
    return func


class HookedLoader(SourceFileLoader):
    def exec_module(self, module: ModuleType) -> None:
        plugin = _current_plugin.get()
        if plugin is None:
            return super().exec_module(module)

        for hook in _before_plugin_load_hooks:
            hook(plugin)
        try:
            super().exec_module(module)
        except Exception as err:
            for hook in _after_plugin_load_hooks:
                hook(plugin, err)
            raise
        else:
            for hook in _after_plugin_load_hooks:
                hook(plugin, None)


def mount_plugin_loader_hook() -> None:
    PluginLoader.__bases__ = (HookedLoader,)


def unmount_plugin_loader_hook() -> None:
    PluginLoader.__bases__ = (SourceFileLoader,)
