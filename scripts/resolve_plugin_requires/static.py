import ast
from pathlib import Path
from typing import Never

from .models import (
    STATIC_UNKNOWN,
    ApiBindings,
    DependencyResolutionError,
    ModuleInfo,
    StaticEnvironment,
    StaticMapping,
    StaticPaths,
    StaticSequence,
    StaticStrings,
    StaticUnknown,
    StaticValue,
)
from .modules import module_package


def static_error(module: ModuleInfo, node: ast.AST, message: str) -> Never:
    raise DependencyResolutionError(
        f"{module.path}:{getattr(node, "lineno", "?")} {message}: {ast.unparse(node)}"
    )


def coerce_static_strings(
    value: StaticValue,
    *,
    convert_paths: bool = False,
) -> StaticStrings | None:
    if isinstance(value, StaticStrings):
        return value
    if convert_paths and isinstance(value, StaticPaths):
        return StaticStrings(frozenset(map(str, value.values)))
    return None


def coerce_static_paths(value: StaticValue) -> StaticPaths | None:
    if isinstance(value, StaticPaths):
        return value
    if isinstance(value, StaticStrings):
        return StaticPaths(frozenset(map(Path, value.values)))
    return None


def static_items(
    value: StaticValue,
    module: ModuleInfo,
    node: ast.AST,
) -> tuple[str | Path, ...]:
    if isinstance(value, StaticStrings):
        return tuple(sorted(value.values))
    if isinstance(value, StaticPaths):
        return tuple(sorted(value.values))
    if isinstance(value, StaticSequence):
        return tuple(
            item for child in value.values for item in static_items(child, module, node)
        )
    static_error(module, node, "Expected finite plugin or path candidates")


def evaluate_static(
    node: ast.AST,
    module: ModuleInfo,
    bindings: ApiBindings,
    environment: StaticEnvironment,
) -> StaticValue:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return StaticStrings(frozenset({node.value}))

    if isinstance(node, ast.Name):
        if node.id == "__file__":
            return StaticPaths(frozenset({module.path}))
        if node.id == "__package__":
            return StaticStrings(frozenset({module_package(module)}))
        if node.id == "__name__":
            static_error(module, node, "__name__ is unsupported; use __package__")
        return environment.get(node.id, STATIC_UNKNOWN)

    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return StaticSequence(
            tuple(
                evaluate_static(item, module, bindings, environment)
                for item in node.elts
            )
        )

    if isinstance(node, ast.Dict):
        values: list[tuple[str, StaticStrings]] = []
        for key_node, value_node in zip(node.keys, node.values, strict=True):
            if not (
                isinstance(key_node, ast.Constant) and isinstance(key_node.value, str)
            ):
                return STATIC_UNKNOWN
            value = evaluate_static(value_node, module, bindings, environment)
            if not isinstance(value, StaticStrings):
                return STATIC_UNKNOWN
            values.append((key_node.value, value))
        return StaticMapping(tuple(values))

    if isinstance(node, ast.NamedExpr):
        if not isinstance(node.target, ast.Name):
            static_error(module, node, "Only named finite assignments are supported")
        value = evaluate_static(node.value, module, bindings, environment)
        bind_static_name(node.target, value, module, environment)
        return value

    if isinstance(node, ast.Subscript):
        mapping = evaluate_static(node.value, module, bindings, environment)
        if not isinstance(mapping, StaticMapping):
            return STATIC_UNKNOWN
        keys = evaluate_static(node.slice, module, bindings, environment)
        if not isinstance(keys, (StaticStrings, StaticUnknown)):
            return STATIC_UNKNOWN
        return mapping.select(keys)

    if isinstance(node, ast.JoinedStr):
        choices = frozenset({""})
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                part_choices = StaticStrings(frozenset({part.value}))
            elif isinstance(part, ast.FormattedValue):
                part_choices = coerce_static_strings(
                    evaluate_static(part.value, module, bindings, environment),
                    convert_paths=True,
                )
                if part_choices is None:
                    return STATIC_UNKNOWN
            else:
                return STATIC_UNKNOWN
            choices = frozenset(
                prefix + suffix for prefix in choices for suffix in part_choices.values
            )
        return StaticStrings(choices)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = coerce_static_paths(
            evaluate_static(node.left, module, bindings, environment)
        )
        right = coerce_static_strings(
            evaluate_static(node.right, module, bindings, environment),
            convert_paths=True,
        )
        if left is None or right is None:
            return STATIC_UNKNOWN
        return StaticPaths(
            frozenset(path / child for path in left.values for child in right.values)
        )

    if isinstance(node, ast.Attribute) and node.attr == "parent":
        paths = coerce_static_paths(
            evaluate_static(node.value, module, bindings, environment)
        )
        if paths is None:
            return STATIC_UNKNOWN
        return StaticPaths(frozenset(path.parent for path in paths.values))

    if isinstance(node, ast.Call):
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in bindings.path_names
            and len(node.args) == 1
        ):
            return (
                coerce_static_paths(
                    evaluate_static(node.args[0], module, bindings, environment)
                )
                or STATIC_UNKNOWN
            )

        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "str"
            and len(node.args) == 1
        ):
            return (
                coerce_static_strings(
                    evaluate_static(node.args[0], module, bindings, environment),
                    convert_paths=True,
                )
                or STATIC_UNKNOWN
            )

        if isinstance(node.func, ast.Attribute):
            value = evaluate_static(
                node.func.value,
                module,
                bindings,
                environment,
            )
            if node.func.attr == "get" and isinstance(value, StaticMapping):
                if not node.args:
                    return STATIC_UNKNOWN
                keys = evaluate_static(node.args[0], module, bindings, environment)
                if not isinstance(keys, (StaticStrings, StaticUnknown)):
                    return STATIC_UNKNOWN
                selected = value.select(keys)
                if len(node.args) > 1:
                    fallback = evaluate_static(
                        node.args[1],
                        module,
                        bindings,
                        environment,
                    )
                    if isinstance(fallback, StaticStrings):
                        selected = StaticStrings(selected.values | fallback.values)
                return selected
            if node.func.attr == "resolve" and not node.args:
                paths = coerce_static_paths(value)
                if paths is None:
                    return STATIC_UNKNOWN
                return StaticPaths(frozenset(path.resolve() for path in paths.values))
            if node.func.attr == "as_posix" and not node.args:
                paths = coerce_static_paths(value)
                if paths is None:
                    return STATIC_UNKNOWN
                return StaticStrings(
                    frozenset(path.as_posix() for path in paths.values)
                )
            if node.func.attr == "joinpath":
                paths = coerce_static_paths(value)
                if paths is None:
                    return STATIC_UNKNOWN
                for arg in node.args:
                    children = coerce_static_strings(
                        evaluate_static(arg, module, bindings, environment),
                        convert_paths=True,
                    )
                    if children is None:
                        return STATIC_UNKNOWN
                    paths = StaticPaths(
                        frozenset(
                            path / child
                            for path in paths.values
                            for child in children.values
                        )
                    )
                return paths

    return STATIC_UNKNOWN


def bind_static_name(
    target: ast.Name,
    value: StaticValue,
    module: ModuleInfo,
    environment: StaticEnvironment,
) -> None:
    if target.id in {"__file__", "__name__", "__package__"}:
        static_error(module, target, f"Cannot redefine magic name {target.id}")
    environment[target.id] = value


def bind_static_target(
    target: ast.expr,
    value: StaticValue,
    module: ModuleInfo,
    environment: StaticEnvironment,
) -> None:
    if isinstance(target, ast.Name):
        bind_static_name(target, value, module, environment)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        if isinstance(value, StaticSequence) and len(target.elts) == len(value.values):
            for child, child_value in zip(target.elts, value.values, strict=True):
                bind_static_target(child, child_value, module, environment)
        else:
            for child in target.elts:
                bind_static_target(child, STATIC_UNKNOWN, module, environment)


def merge_static_values(left: StaticValue, right: StaticValue) -> StaticValue:
    if isinstance(left, StaticStrings) and isinstance(right, StaticStrings):
        return StaticStrings(left.values | right.values)
    if isinstance(left, StaticPaths) and isinstance(right, StaticPaths):
        return StaticPaths(left.values | right.values)
    if left == right:
        return left
    return STATIC_UNKNOWN


def merge_static_environments(
    left: StaticEnvironment,
    right: StaticEnvironment,
) -> StaticEnvironment:
    return {
        name: merge_static_values(
            left.get(name, STATIC_UNKNOWN),
            right.get(name, STATIC_UNKNOWN),
        )
        for name in left.keys() | right.keys()
    }
