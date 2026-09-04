import ast
from collections.abc import Sequence
from pathlib import Path

from .models import (
    ROOT,
    STATIC_UNKNOWN,
    ApiBindings,
    DependencyResolutionError,
    ModuleInfo,
    PluginLoadRequest,
    PluginUnit,
    StaticEnvironment,
)
from .modules import (
    add_plugin_unit,
    get_api_bindings,
    import_targets,
    is_api_call,
    iter_root_modules,
    managed_dependency,
    module_name_from_path,
    module_owner,
    plugin_id_for_module,
)
from .static import (
    bind_static_target,
    evaluate_static,
    merge_static_environments,
    static_error,
    static_items,
)


class PluginLoadAnalyzer:
    def __init__(self, module: ModuleInfo, bindings: ApiBindings) -> None:
        self.module = module
        self.bindings = bindings
        self.requests: list[PluginLoadRequest] = []

    def analyze(self) -> list[PluginLoadRequest]:
        self._statements(self.module.tree.body, {})
        return self.requests

    def _statements(
        self,
        statements: Sequence[ast.stmt],
        environment: StaticEnvironment,
    ) -> None:
        for statement in statements:
            if isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                continue

            if isinstance(statement, ast.Assign):
                self._expression(statement.value, environment)
                value = evaluate_static(
                    statement.value,
                    self.module,
                    self.bindings,
                    environment,
                )
                for target in statement.targets:
                    bind_static_target(target, value, self.module, environment)
                continue

            if isinstance(statement, ast.AnnAssign):
                if statement.value is not None:
                    self._expression(statement.value, environment)
                    value = evaluate_static(
                        statement.value,
                        self.module,
                        self.bindings,
                        environment,
                    )
                else:
                    value = STATIC_UNKNOWN
                bind_static_target(statement.target, value, self.module, environment)
                continue

            if isinstance(statement, ast.AugAssign):
                bind_static_target(
                    statement.target,
                    STATIC_UNKNOWN,
                    self.module,
                    environment,
                )
                continue

            if isinstance(statement, ast.Expr):
                self._expression(statement.value, environment)
                continue

            if isinstance(statement, ast.If):
                self._expression(statement.test, environment)
                body_environment = dict(environment)
                else_environment = dict(environment)
                self._statements(statement.body, body_environment)
                self._statements(statement.orelse, else_environment)
                environment.clear()
                environment.update(
                    merge_static_environments(body_environment, else_environment)
                )
                continue

            if isinstance(statement, (ast.For, ast.AsyncFor)):
                self._expression(statement.iter, environment)
                body_environment = dict(environment)
                bind_static_target(
                    statement.target,
                    STATIC_UNKNOWN,
                    self.module,
                    body_environment,
                )
                self._statements(statement.body, body_environment)
                else_environment = dict(environment)
                self._statements(statement.orelse, else_environment)
                environment.clear()
                environment.update(
                    merge_static_environments(body_environment, else_environment)
                )
                continue

            if isinstance(statement, ast.While):
                self._expression(statement.test, environment)
                body_environment = dict(environment)
                else_environment = dict(environment)
                self._statements(statement.body, body_environment)
                self._statements(statement.orelse, else_environment)
                environment.clear()
                environment.update(
                    merge_static_environments(body_environment, else_environment)
                )
                continue

            if isinstance(statement, ast.Try):
                branches: list[StaticEnvironment] = []
                body_environment = dict(environment)
                self._statements(statement.body, body_environment)
                self._statements(statement.orelse, body_environment)
                branches.append(body_environment)
                for handler in statement.handlers:
                    handler_environment = dict(environment)
                    self._statements(handler.body, handler_environment)
                    branches.append(handler_environment)
                merged = branches[0]
                for branch in branches[1:]:
                    merged = merge_static_environments(merged, branch)
                self._statements(statement.finalbody, merged)
                environment.clear()
                environment.update(merged)
                continue

            if isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    self._expression(item.context_expr, environment)
                self._statements(statement.body, environment)
                continue

            if isinstance(statement, ast.Match):
                self._expression(statement.subject, environment)
                branches: list[StaticEnvironment] = []
                for case in statement.cases:
                    case_environment = dict(environment)
                    if case.guard is not None:
                        self._expression(case.guard, case_environment)
                    self._statements(case.body, case_environment)
                    branches.append(case_environment)
                if branches:
                    merged = branches[0]
                    for branch in branches[1:]:
                        merged = merge_static_environments(merged, branch)
                    environment.clear()
                    environment.update(merged)

    def _expression(
        self,
        node: ast.AST,
        environment: StaticEnvironment,
    ) -> None:
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, ast.NamedExpr):
            self._expression(node.value, environment)
            evaluate_static(node, self.module, self.bindings, environment)
            return
        if isinstance(node, ast.Call) and self._record_plugin_call(node, environment):
            return
        for child in ast.iter_child_nodes(node):
            self._expression(child, environment)

    def _record_plugin_call(
        self,
        call: ast.Call,
        environment: StaticEnvironment,
    ) -> bool:
        for name in ("load_plugin", "load_plugins", "load_all_plugins"):
            if not is_api_call(call, name, self.bindings):
                continue
            if name == "load_plugin":
                if not call.args:
                    static_error(self.module, call, "load_plugin() has no module")
                value = evaluate_static(
                    call.args[0],
                    self.module,
                    self.bindings,
                    environment,
                )
                self.requests.append(
                    PluginLoadRequest(
                        modules=static_items(value, self.module, call.args[0])
                    )
                )
                return True

            if name == "load_plugins":
                if not call.args:
                    static_error(self.module, call, "load_plugins() has no path")
                directories = tuple(
                    item
                    for arg in call.args
                    for item in static_items(
                        evaluate_static(
                            arg,
                            self.module,
                            self.bindings,
                            environment,
                        ),
                        self.module,
                        arg,
                    )
                )
                self.requests.append(PluginLoadRequest(directories=directories))
                return True

            module_arg = call.args[0] if call.args else None
            directory_arg = call.args[1] if len(call.args) > 1 else None
            for keyword in call.keywords:
                if keyword.arg == "module_path":
                    module_arg = keyword.value
                elif keyword.arg == "plugin_dir":
                    directory_arg = keyword.value
            modules = (
                static_items(
                    evaluate_static(
                        module_arg,
                        self.module,
                        self.bindings,
                        environment,
                    ),
                    self.module,
                    module_arg,
                )
                if module_arg is not None
                else ()
            )
            directories = (
                static_items(
                    evaluate_static(
                        directory_arg,
                        self.module,
                        self.bindings,
                        environment,
                    ),
                    self.module,
                    directory_arg,
                )
                if directory_arg is not None
                else ()
            )
            self.requests.append(
                PluginLoadRequest(modules=modules, directories=directories)
            )
            return True
        return False


def resolve_search_path(value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def discover_directory_modules(
    directory: Path,
    modules: dict[str, ModuleInfo],
) -> list[str]:
    if not directory.is_dir():
        raise DependencyResolutionError(
            f"Plugin search path does not exist: {directory}"
        )
    result: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.name.startswith("_"):
            continue
        source = (
            path
            if path.is_file() and path.suffix == ".py"
            else path / "__init__.py"
            if path.is_dir() and (path / "__init__.py").is_file()
            else None
        )
        if source is None:
            continue
        module_name = module_name_from_path(source)
        if module_name in modules:
            result.append(module_name)
    return result


def collect_eager_modules(
    unit: PluginUnit,
    units: dict[str, PluginUnit],
    modules: dict[str, ModuleInfo],
) -> set[str]:
    pending = [unit.entry_module]
    visited: set[str] = set()
    while pending:
        module_name = pending.pop()
        if module_name in visited:
            continue
        visited.add(module_name)
        module = modules[module_name]
        for node in module.tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in import_targets(module, node, modules):
                target_owner = module_owner(target, units)
                if (
                    target in modules
                    and target_owner is not None
                    and target_owner.id == unit.id
                ):
                    pending.append(target)
    return visited


def add_discovered_module(
    module_name: str,
    units: dict[str, PluginUnit],
    entry_modules: dict[str, str],
    modules: dict[str, ModuleInfo],
) -> bool:
    if module_name not in modules:
        raise DependencyResolutionError(
            f"Plugin loader references non-local module {module_name!r}; "
            "use require() for dependencies"
        )
    plugin_id, parent_id = plugin_id_for_module(module_name, units)
    return add_plugin_unit(
        units,
        entry_modules,
        PluginUnit(plugin_id, module_name, parent_id),
    )


def discover_plugin_units(
    modules: dict[str, ModuleInfo],
) -> dict[str, PluginUnit]:
    units: dict[str, PluginUnit] = {}
    entry_modules: dict[str, str] = {}
    for module_name in iter_root_modules():
        plugin_id = module_name.rsplit(".", 1)[-1]
        add_plugin_unit(
            units,
            entry_modules,
            PluginUnit(plugin_id, module_name),
        )

    while True:
        changed = False
        for unit in list(units.values()):
            for module_name in collect_eager_modules(unit, units, modules):
                module = modules[module_name]
                bindings = get_api_bindings(module)
                requests = PluginLoadAnalyzer(module, bindings).analyze()
                for request in requests:
                    for value in request.modules:
                        candidate = str(value)
                        if isinstance(value, Path) or candidate.endswith(".py"):
                            candidate = module_name_from_path(Path(value))
                        changed |= add_discovered_module(
                            candidate,
                            units,
                            entry_modules,
                            modules,
                        )
                    for value in request.directories:
                        directory = resolve_search_path(value)
                        for child in discover_directory_modules(directory, modules):
                            changed |= add_discovered_module(
                                child,
                                units,
                                entry_modules,
                                modules,
                            )
        if not changed:
            return units


def collect_automatic_dependencies(
    unit: PluginUnit,
    units: dict[str, PluginUnit],
    modules: dict[str, ModuleInfo],
) -> tuple[set[str], set[str]]:
    eager_modules = collect_eager_modules(unit, units, modules)
    dependencies: set[str] = set()
    for module_name in eager_modules:
        module = modules[module_name]
        for node in module.tree.body:
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for target in import_targets(module, node, modules):
                if dependency := managed_dependency(target, unit, units):
                    dependencies.add(dependency)
    return dependencies, eager_modules
