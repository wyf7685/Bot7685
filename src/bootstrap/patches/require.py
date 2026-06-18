import ast
import functools
import importlib
import importlib.metadata
import itertools
import linecache
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


class _ImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.add(alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and not node.level:
            self.imports.add(node.module)

    @classmethod
    def collect(cls, file: Path) -> set[str]:
        filename = str(file)
        try:
            lines = linecache.getlines(filename)
            module = ast.parse("".join(lines), filename, mode="exec")
        except Exception:
            return set()
        collector = cls()
        collector.visit(module)
        return collector.imports


def _resolve_requires(path: Path, *, seen: set[Path] | None = None) -> set[str]:
    if seen is None:
        seen = set()
    elif path in seen:
        return set()
    seen.add(path)
    if not path.exists():
        return set()
    if path.is_dir():
        return set(
            itertools.chain.from_iterable(
                _resolve_requires(item, seen=seen) for item in path.iterdir()
            )
        )
    if path.suffix != ".py" or not path.is_file():
        return set()

    requires: set[str] = set()
    for name in _ImportCollector.collect(path):
        if name.startswith("nonebot_plugin_"):
            requires.add(name.split(".")[0])
        elif name.startswith(("src.plugins.", "src.service.")):
            requires.add(".".join(name.split(".")[:3]))

    if path.stem == "__init__":
        requires.update(_resolve_requires(path.parent, seen=seen))

    return requires


@on_plugin_load("before")
def _auto_requires(plugin: Plugin) -> None:
    file = plugin.module.__file__
    if not file:
        return

    for req in sorted(_resolve_requires(Path(file))):
        if req.startswith("nonebot_plugin_"):
            try:
                importlib.metadata.distribution(req)
            except importlib.metadata.PackageNotFoundError:
                continue
        _patched_require(req)
