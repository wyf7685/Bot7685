import importlib

import nonebot

ADAPTERS = {
    "Discord": "discord",
    "Feishu": "feishu",
    "Milky": "milky",
    "OneBot V11": "onebot11",
    "QQ": "qq",
    "Satori": "satori",
    "Telegram": "telegram",
}


def __init() -> None:
    logger = nonebot.logger.opt(colors=True)
    for adapter in nonebot.get_adapters():
        if module := ADAPTERS.get(adapter):
            logger.info(f"Patch event for adapter <g>{adapter}</>")
            importlib.import_module(f"{__package__}.{module}")


__init()
del __init
