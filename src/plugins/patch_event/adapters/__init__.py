def __load() -> None:
    from contextlib import suppress

    with suppress(ImportError):
        from . import discord as discord
    with suppress(ImportError):
        from . import onebot11 as onebot11
    with suppress(ImportError):
        from . import qq as qq
    with suppress(ImportError):
        from . import satori as satori
    with suppress(ImportError):
        from . import telegram as telegram


__load()
