from nonebot import get_adapters

__all__: list[str] = []

if "Milky" in get_adapters():
    from . import milky as milky

    __all__ += ["milky"]
