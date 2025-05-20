import importlib
import sys
import weakref


def lazy_import(location: dict[str, str], depth: int = 1) -> None:
    globalns = sys._getframe(depth).f_globals  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    module_name: str = globalns["__name__"]
    package: str = globalns["__package__"]

    def get(name: str) -> object:
        if (ns := ns_ref()) is None or (cache := cache_ref()) is None:
            raise RuntimeError("lazy_import has been garbage collected")

        if name in ns:
            return ns[name]
        if name in location:
            if name not in cache:
                module = importlib.import_module(f".{location[name]}", package)
                cache[name] = getattr(module, name)
            return cache[name]
        raise AttributeError(f"module {module_name} has no attribute {name}")

    globalns["__lazy_import_cache__"] = cache = dict[str, object]()
    globalns["__getattr__"] = get
    globalns["__all__"] = list(location.keys())
    globalns.pop(next(k for k, v in globalns.items() if v is lazy_import))

    ns_ref = weakref.ref(globalns)
    cache_ref = weakref.ref(cache)
    del globalns, cache
