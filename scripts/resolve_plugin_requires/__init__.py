from .audit import DependencyAuditor
from .loading import collect_automatic_dependencies, discover_plugin_units
from .modules import build_module_index

__all__ = ["resolve_plugin_requires"]


def resolve_plugin_requires() -> dict[str, list[str]]:
    modules = build_module_index()
    units = discover_plugin_units(modules)
    automatic: dict[str, set[str]] = {}
    eager_modules: dict[str, set[str]] = {}
    for plugin_id, unit in units.items():
        dependencies, eager = collect_automatic_dependencies(unit, units, modules)
        automatic[plugin_id] = dependencies
        eager_modules[plugin_id] = eager

    DependencyAuditor(units, modules, automatic, eager_modules).audit()
    return {plugin_id: sorted(automatic[plugin_id]) for plugin_id in sorted(units)}
