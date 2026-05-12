import importlib

import nonebot

from . import common as common

ADAPTERS = {
    "Discord": "discord",
    "Milky": "milky",
    "OneBot V11": "onebot11",
    "Telegram": "telegram",
}


def __init() -> None:
    for adapter in nonebot.get_adapters():
        if module := ADAPTERS.get(adapter):
            importlib.import_module(f"{__package__}.{module}")


__init()
del __init
