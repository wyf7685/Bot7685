import importlib
import sys


def lazy_import(location: dict[str, str], depth: int = 1) -> None:
    globalns = sys._getframe(depth).f_globals  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    module_name: str = globalns["__name__"]
    package: str = globalns["__package__"]

    cache: dict[str, object] = {}

    def get(name: str) -> object:
        if name in globalns:
            return globalns[name]
        if name in location:
            if name not in cache:
                module = importlib.import_module(f".{location[name]}", package)
                cache[name] = getattr(module, name)
            return cache[name]
        raise AttributeError(f"module {module_name} has no attribute {name}")

    globalns["__getattr__"] = get
    globalns["__all__"] = list(location.keys())
    globalns.pop(next(k for k, v in globalns.items() if v is lazy_import))
