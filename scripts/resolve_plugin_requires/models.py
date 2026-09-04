import ast
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
SOURCE_ROOTS = (SRC / "plugins", SRC / "service")
PLUGIN_API_MODULES = {"nonebot", "nonebot.plugin", "nonebot.plugin.load"}


class DependencyResolutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModuleInfo:
    name: str
    path: Path
    is_package: bool
    tree: ast.Module


@dataclass(frozen=True, slots=True)
class PluginUnit:
    id: str
    entry_module: str
    parent_id: str | None = None


@dataclass(frozen=True, slots=True)
class ApiBindings:
    nonebot_names: frozenset[str]
    importlib_names: frozenset[str]
    import_module_names: frozenset[str]
    path_names: frozenset[str]
    require_names: frozenset[str]
    loader_names: dict[str, frozenset[str]]


@dataclass(frozen=True, slots=True)
class StaticStrings:
    values: frozenset[str]


@dataclass(frozen=True, slots=True)
class StaticPaths:
    values: frozenset[Path]


@dataclass(frozen=True, slots=True)
class StaticSequence:
    values: tuple[StaticValue, ...]


@dataclass(frozen=True, slots=True)
class StaticMapping:
    values: tuple[tuple[str, StaticStrings], ...]

    def select(self, keys: StaticStrings | StaticUnknown) -> StaticStrings:
        mapping = dict(self.values)
        if isinstance(keys, StaticUnknown):
            selected = mapping.values()
        else:
            selected = (mapping[key] for key in keys.values if key in mapping)
        return StaticStrings(
            frozenset(value for choices in selected for value in choices.values)
        )


@dataclass(frozen=True, slots=True)
class StaticUnknown:
    pass


STATIC_UNKNOWN = StaticUnknown()
type StaticValue = (
    StaticStrings | StaticPaths | StaticSequence | StaticMapping | StaticUnknown
)
type StaticEnvironment = dict[str, StaticValue]


@dataclass(frozen=True, slots=True)
class PluginLoadRequest:
    modules: tuple[str | Path, ...] = ()
    directories: tuple[str | Path, ...] = ()
