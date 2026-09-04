import ast
from collections.abc import Sequence

from .models import ApiBindings, DependencyResolutionError, ModuleInfo, PluginUnit
from .modules import (
    get_api_bindings,
    import_targets,
    is_import_module_call,
    is_require_call,
    managed_dependency,
    module_owner,
)


def normalize_requirement(name: str, units: dict[str, PluginUnit]) -> str:
    if unit := units.get(name):
        return unit.entry_module
    if name.startswith("nonebot_plugin_"):
        return name.split(".", 1)[0]
    return name


def literal_strings(node: ast.AST) -> set[str] | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        result: set[str] = set()
        for item in node.elts:
            values = literal_strings(item)
            if values is None:
                return None
            result.update(values)
        return result
    return None


def optional_plugin_ids(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    result: set[str] = set()
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        name = (
            decorator.func.id
            if isinstance(decorator.func, ast.Name)
            else decorator.func.attr
            if isinstance(decorator.func, ast.Attribute)
            else ""
        )
        if name != "on_plugin_load":
            continue
        for keyword in decorator.keywords:
            if keyword.arg == "plugin_id" and (
                values := literal_strings(keyword.value)
            ):
                result.update(values)
    return result


def is_type_checking(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "TYPE_CHECKING") or (
        isinstance(node, ast.Attribute) and node.attr == "TYPE_CHECKING"
    )


class DependencyAuditor:
    def __init__(
        self,
        units: dict[str, PluginUnit],
        modules: dict[str, ModuleInfo],
        automatic: dict[str, set[str]],
        eager_modules: dict[str, set[str]],
    ) -> None:
        self.units = units
        self.modules = modules
        self.automatic = automatic
        self.eager_modules = eager_modules
        self.errors: list[str] = []
        self._audited: set[tuple[str, frozenset[str]]] = set()
        self._reached: set[str] = set()

    def audit(self) -> None:
        for unit in self.units.values():
            self._audit_module(unit.entry_module, set())
        for module_name in self.modules:
            owner = module_owner(module_name, self.units)
            if owner is not None and module_name not in self._reached:
                self._audit_module(module_name, set())
        self._audit_dynamic_imports()
        if self.errors:
            details = "\n".join(f"- {error}" for error in sorted(set(self.errors)))
            raise DependencyResolutionError(
                "Uncovered or unsafe plugin dependencies:\n" + details
            )

    def _audit_module(self, module_name: str, inherited: set[str]) -> None:
        key = (module_name, frozenset(inherited))
        if key in self._audited:
            return
        self._audited.add(key)
        self._reached.add(module_name)
        module = self.modules[module_name]
        bindings = get_api_bindings(module)
        self._audit_statements(
            module,
            module.tree.body,
            bindings,
            set(inherited),
            direct=True,
            optional=frozenset(),
        )

    def _audit_statements(
        self,
        module: ModuleInfo,
        statements: Sequence[ast.stmt],
        bindings: ApiBindings,
        requirements: set[str],
        *,
        direct: bool,
        optional: frozenset[str],
    ) -> set[str]:
        current = set(requirements)
        owner = module_owner(module.name, self.units)
        assert owner is not None
        for statement in statements:
            if (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Call)
                and is_require_call(statement.value, bindings)
            ):
                call = statement.value
                values = literal_strings(call.args[0]) if call.args else None
                if values is None:
                    self.errors.append(
                        f"{module.path}:{statement.lineno} require() needs a "
                        "literal plugin name"
                    )
                else:
                    current.update(
                        normalize_requirement(value, self.units) for value in values
                    )
                continue

            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                self._audit_import(
                    module,
                    statement,
                    owner,
                    current,
                    direct=direct,
                    optional=optional,
                )
                continue

            if isinstance(statement, ast.If):
                if is_type_checking(statement.test):
                    continue
                self._audit_statements(
                    module,
                    statement.body,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                self._audit_statements(
                    module,
                    statement.orelse,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                continue

            if isinstance(statement, ast.Try):
                body_requirements = self._audit_statements(
                    module,
                    statement.body,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                for handler in statement.handlers:
                    self._audit_statements(
                        module,
                        handler.body,
                        bindings,
                        set(current),
                        direct=False,
                        optional=optional,
                    )
                self._audit_statements(
                    module,
                    statement.orelse,
                    bindings,
                    body_requirements,
                    direct=False,
                    optional=optional,
                )
                self._audit_statements(
                    module,
                    statement.finalbody,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                continue

            if isinstance(statement, (ast.With, ast.AsyncWith)):
                self._audit_statements(
                    module,
                    statement.body,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                continue

            if isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                self._audit_statements(
                    module,
                    statement.body,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                self._audit_statements(
                    module,
                    statement.orelse,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
                continue

            if isinstance(statement, ast.Match):
                for case in statement.cases:
                    self._audit_statements(
                        module,
                        case.body,
                        bindings,
                        set(current),
                        direct=False,
                        optional=optional,
                    )
                continue

            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._audit_runtime_node(
                    module,
                    statement,
                    bindings,
                    current,
                    frozenset(optional_plugin_ids(statement)),
                )
                continue

            if isinstance(statement, ast.ClassDef):
                self._audit_statements(
                    module,
                    statement.body,
                    bindings,
                    set(current),
                    direct=False,
                    optional=optional,
                )
        return current

    def _audit_import(
        self,
        module: ModuleInfo,
        node: ast.Import | ast.ImportFrom,
        owner: PluginUnit,
        requirements: set[str],
        *,
        direct: bool,
        optional: frozenset[str],
    ) -> None:
        for target in import_targets(module, node, self.modules):
            if dependency := managed_dependency(target, owner, self.units):
                automatic = self.automatic[owner.id]
                is_automatic = direct and module.name in self.eager_modules[owner.id]
                if (
                    not is_automatic
                    and dependency not in automatic
                    and dependency not in requirements
                    and dependency not in optional
                ):
                    self.errors.append(
                        f"{module.path}:{node.lineno} imports {dependency!r} "
                        f"outside {owner.id!r}'s eager module closure without "
                        "an earlier require()"
                    )
                continue

            target_owner = module_owner(target, self.units)
            if (
                target in self.modules
                and target_owner is not None
                and target_owner.id == owner.id
                and target != module.name
            ):
                self._audit_module(target, set(requirements))

    def _audit_runtime_node(
        self,
        module: ModuleInfo,
        node: ast.AST,
        bindings: ApiBindings,
        requirements: set[str],
        optional: frozenset[str],
    ) -> None:
        owner = module_owner(module.name, self.units)
        assert owner is not None
        if isinstance(node, ast.If) and is_type_checking(node.test):
            return
        if isinstance(node, ast.Call) and is_require_call(node, bindings):
            self.errors.append(
                f"{module.path}:{node.lineno} calls require() at runtime; "
                "declare the dependency while the plugin is loading"
            )
            return
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for target in import_targets(module, node, self.modules):
                if (
                    (dependency := managed_dependency(target, owner, self.units))
                    and dependency not in self.automatic[owner.id]
                    and dependency not in requirements
                    and dependency not in optional
                ):
                    self.errors.append(
                        f"{module.path}:{node.lineno} imports {dependency!r} "
                        "at runtime without a load-time require()"
                    )
            return
        for child in ast.iter_child_nodes(node):
            self._audit_runtime_node(
                module,
                child,
                bindings,
                requirements,
                optional,
            )

    def _audit_dynamic_imports(self) -> None:
        for module in self.modules.values():
            owner = module_owner(module.name, self.units)
            if owner is None:
                continue
            bindings = get_api_bindings(module)
            for node in ast.walk(module.tree):
                if not isinstance(node, ast.Call) or not is_import_module_call(
                    node, bindings
                ):
                    continue
                if not node.args or not self._is_local_dynamic_target(
                    node.args[0], owner
                ):
                    self.errors.append(
                        f"{module.path}:{node.lineno} has an unresolved dynamic "
                        f"import target: {ast.unparse(node)}"
                    )

    @staticmethod
    def _is_local_dynamic_target(node: ast.AST, owner: PluginUnit) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value == owner.entry_module or node.value.startswith(
                f"{owner.entry_module}."
            )
        if not isinstance(node, ast.JoinedStr):
            return False
        return any(
            isinstance(value, ast.FormattedValue)
            and isinstance(value.value, ast.Name)
            and value.value.id == "__package__"
            for value in node.values
        )
