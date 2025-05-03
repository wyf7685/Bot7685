import importlib

import nonebot

ADAPTERS = {
    "Discord": "discord",
    "Feishu": "feishu",
    "OneBot V11": "onebot11",
    "QQ": "qq",
    "Satori": "satori",
    "Telegram": "telegram",
}


[
    importlib.import_module(f"{__package__}.{module}")
    for adapter in nonebot.get_adapters()
    if (module := ADAPTERS.get(adapter))
]
