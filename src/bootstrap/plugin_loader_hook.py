from collections.abc import Callable
from importlib.machinery import SourceFileLoader
from types import ModuleType

from nonebot.plugin import Plugin
from nonebot.plugin.manager import PluginLoader

type BeforePluginLoadHook = Callable[[ModuleType, Plugin], object]
type AfterPluginLoadHook = Callable[[ModuleType, Plugin, Exception | None], object]


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
        plugin: Plugin | None = getattr(module, "__plugin__", None)

        if plugin is not None:
            for hook in _before_plugin_load_hooks:
                hook(module, plugin)

        try:
            super().exec_module(module)
        except Exception as err:
            if plugin is not None:
                for hook in _after_plugin_load_hooks:
                    hook(module, plugin, err)
            raise
        else:
            if plugin is not None:
                for hook in _after_plugin_load_hooks:
                    hook(module, plugin, None)


def mount_plugin_loader_hook() -> None:
    PluginLoader.__bases__ = (HookedLoader,)


def unmount_plugin_loader_hook() -> None:
    PluginLoader.__bases__ = (SourceFileLoader,)
