import ast
from collections.abc import Iterator
from pathlib import Path

from .models import (
    PLUGIN_API_MODULES,
    ROOT,
    SOURCE_ROOTS,
    ApiBindings,
    DependencyResolutionError,
    ModuleInfo,
    PluginUnit,
)


def module_name_from_path(path: Path) -> str:
    relative = path.resolve().relative_to(ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def build_module_index() -> dict[str, ModuleInfo]:
    modules: dict[str, ModuleInfo] = {}
    for source_root in SOURCE_ROOTS:
        for path in sorted(source_root.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            try:
                tree = ast.parse(
                    path.read_text(encoding="utf-8"),
                    str(path),
                    mode="exec",
                )
            except (OSError, SyntaxError) as exc:
                raise DependencyResolutionError(
                    f"Failed to parse source module {path}: {exc}"
                ) from exc
            name = module_name_from_path(path)
            modules[name] = ModuleInfo(
                name=name,
                path=path,
                is_package=path.name == "__init__.py",
                tree=tree,
            )
    return modules


def iter_root_modules() -> Iterator[str]:
    for source_root in SOURCE_ROOTS:
        for path in sorted(source_root.iterdir()):
            if (
                path.is_file()
                and path.suffix == ".py"
                and not path.stem.startswith("_")
            ):
                yield module_name_from_path(path)
            elif path.is_dir() and (path / "__init__.py").is_file():
                yield module_name_from_path(path / "__init__.py")


def add_plugin_unit(
    units: dict[str, PluginUnit],
    entry_modules: dict[str, str],
    unit: PluginUnit,
) -> bool:
    if existing := units.get(unit.id):
        if existing.entry_module != unit.entry_module:
            raise DependencyResolutionError(
                f"Plugin ID {unit.id!r} maps to both "
                f"{existing.entry_module!r} and {unit.entry_module!r}"
            )
        return False
    if existing_id := entry_modules.get(unit.entry_module):
        raise DependencyResolutionError(
            f"Module {unit.entry_module!r} is already controlled by "
            f"plugin {existing_id!r}"
        )
    units[unit.id] = unit
    entry_modules[unit.entry_module] = unit.id
    return True


def find_parent_unit(
    module_name: str,
    units: dict[str, PluginUnit],
) -> PluginUnit | None:
    candidates = [
        unit
        for unit in units.values()
        if module_name.startswith(f"{unit.entry_module}.")
    ]
    return (
        max(candidates, key=lambda unit: unit.entry_module.count("."))
        if candidates
        else None
    )


def plugin_id_for_module(
    module_name: str,
    units: dict[str, PluginUnit],
) -> tuple[str, str | None]:
    name = module_name.rsplit(".", 1)[-1]
    if parent := find_parent_unit(module_name, units):
        return f"{parent.id}:{name}", parent.id
    return name, None


def module_owner(
    module_name: str,
    units: dict[str, PluginUnit],
) -> PluginUnit | None:
    candidates = [
        unit
        for unit in units.values()
        if module_name == unit.entry_module
        or module_name.startswith(f"{unit.entry_module}.")
    ]
    return (
        max(candidates, key=lambda unit: unit.entry_module.count("."))
        if candidates
        else None
    )


def is_ancestor_unit(
    candidate: PluginUnit,
    unit: PluginUnit,
    units: dict[str, PluginUnit],
) -> bool:
    parent_id = unit.parent_id
    while parent_id is not None:
        if parent_id == candidate.id:
            return True
        parent_id = units[parent_id].parent_id
    return False


def module_package(module: ModuleInfo) -> str:
    return module.name if module.is_package else module.name.rsplit(".", 1)[0]


def resolve_import_from(module: ModuleInfo, node: ast.ImportFrom) -> str | None:
    if node.level == 0:
        return node.module
    parts = module_package(module).split(".")
    keep = len(parts) - node.level + 1
    if keep < 0:
        return None
    base = ".".join(parts[:keep])
    return f"{base}.{node.module}" if node.module else base


def import_targets(
    module: ModuleInfo,
    node: ast.Import | ast.ImportFrom,
    modules: dict[str, ModuleInfo],
) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}

    base = resolve_import_from(module, node)
    if base is None:
        return set()
    targets = {base}
    for alias in node.names:
        candidate = f"{base}.{alias.name}"
        if candidate in modules:
            targets.add(candidate)
    return targets


def managed_dependency(
    target: str,
    owner: PluginUnit,
    units: dict[str, PluginUnit],
) -> str | None:
    if target.startswith("nonebot_plugin_"):
        return target.split(".", 1)[0]
    target_owner = module_owner(target, units)
    if (
        target_owner is not None
        and target_owner.id != owner.id
        and not is_ancestor_unit(target_owner, owner, units)
    ):
        return target_owner.entry_module
    return None


def get_api_bindings(module: ModuleInfo) -> ApiBindings:
    nonebot_names: set[str] = set()
    importlib_names: set[str] = set()
    import_module_names: set[str] = set()
    path_names: set[str] = set()
    require_names: set[str] = set()
    loader_names = {
        "load_plugin": set(),
        "load_plugins": set(),
        "load_all_plugins": set(),
    }

    for node in module.tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound_name = alias.asname or alias.name.split(".", 1)[0]
                if alias.name == "nonebot":
                    nonebot_names.add(bound_name)
                elif alias.name == "importlib":
                    importlib_names.add(bound_name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "pathlib":
                for alias in node.names:
                    if alias.name == "Path":
                        path_names.add(alias.asname or alias.name)
            elif node.module == "importlib":
                for alias in node.names:
                    if alias.name == "import_module":
                        import_module_names.add(alias.asname or alias.name)
            elif node.module in PLUGIN_API_MODULES:
                for alias in node.names:
                    bound_name = alias.asname or alias.name
                    if alias.name == "require":
                        require_names.add(bound_name)
                    elif alias.name in loader_names:
                        loader_names[alias.name].add(bound_name)

    return ApiBindings(
        nonebot_names=frozenset(nonebot_names),
        importlib_names=frozenset(importlib_names),
        import_module_names=frozenset(import_module_names),
        path_names=frozenset(path_names),
        require_names=frozenset(require_names),
        loader_names={name: frozenset(values) for name, values in loader_names.items()},
    )


def is_api_call(call: ast.Call, name: str, bindings: ApiBindings) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in bindings.loader_names.get(name, ())
    return (
        isinstance(func, ast.Attribute)
        and func.attr == name
        and isinstance(func.value, ast.Name)
        and func.value.id in bindings.nonebot_names
    )


def is_require_call(call: ast.Call, bindings: ApiBindings) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in bindings.require_names
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "require"
        and isinstance(func.value, ast.Name)
        and func.value.id in bindings.nonebot_names
    )


def is_import_module_call(call: ast.Call, bindings: ApiBindings) -> bool:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id in bindings.import_module_names
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "import_module"
        and isinstance(func.value, ast.Name)
        and func.value.id in bindings.importlib_names
    )
