import sys


def lazy_import(location: dict[str, str]) -> None:
    globalns = sys._getframe(1).f_globals  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    _name_ = globalns["__name__"]
    _package_ = globalns["__package__"]

    cache: dict[str, object] = {}

    def get(name: str) -> object:
        if name in globalns:
            return globalns[name]
        if name in location:
            if name not in cache:
                import importlib

                module = importlib.import_module(f".{location[name]}", _package_)
                cache[name] = getattr(module, name)
            return cache[name]
        raise AttributeError(f"module {_name_} has no attribute {name}")

    globalns["__getattr__"] = get
    globalns["__all__"] = list(location.keys())
