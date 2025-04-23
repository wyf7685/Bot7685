import importlib

import nonebot
import nonebot.utils

ADAPTERS = {
    "Discord": "discord",
    "Feishu": "feishu",
    "OneBot V11": "onebot11",
    "QQ": "qq",
    "Satori": "satori",
    "Telegram": "telegram",
}

for adapter in nonebot.get_adapters():
    if module := ADAPTERS.get(adapter):
        try:
            importlib.import_module(f".{module}", __package__)
        except ImportError as e:
            nonebot.logger.opt(colors=True).warning(
                f"Failed to load patcher for <g>{adapter}</g>:"
                f" <r>{nonebot.utils.escape_tag(str(e))}</r>"
            )
