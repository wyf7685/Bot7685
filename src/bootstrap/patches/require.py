import functools
import importlib
import importlib.metadata
import json
from collections import defaultdict
from pathlib import Path
from types import ModuleType

from bot7685_ext.nonebot import on_plugin_load
from nonebot.plugin import Plugin
from nonebot.plugin import _current_plugin as current_plugin
from nonebot.plugin import require as original_require

_plugin_deps: dict[str, set[str]] = defaultdict(set)


@functools.wraps(original_require)
def _patched_require(name: str) -> ModuleType:
    module = original_require(name)
    plugin: Plugin | None = getattr(module, "__plugin__", None)
    current = current_plugin.get()
    if plugin and current and plugin.id_ != current.id_:
        _plugin_deps[current.id_].add(plugin.id_)
    return module


def get_plugin_deps() -> dict[str, set[str]]:
    return _plugin_deps


def patch_require() -> None:
    for name in ("nonebot", "nonebot.plugin", "nonebot.plugin.load"):
        module = importlib.import_module(name)
        setattr(module, "require", _patched_require)  # noqa: B010


_requires_file = Path(__file__).resolve().parent / "plugin_requires.json"
if not _requires_file.exists():
    raise FileNotFoundError(f"Required file not found: {_requires_file}")
_requires: dict[str, list[str]] = json.loads(_requires_file.read_text(encoding="utf-8"))


@on_plugin_load("before")
def _auto_requires(plugin: Plugin) -> None:
    if plugin.id_ not in _requires:
        return

    for req in _requires[plugin.id_]:
        _patched_require(req)
