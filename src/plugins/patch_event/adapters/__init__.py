import nonebot

from ..patcher import patcher as patcher

ADAPTER_PLUGINS = {
    "Discord": "discord",
    "Feishu": "feishu",
    "GitHub": "github",
    "Milky": "milky",
    "OneBot V11": "onebot11",
    "QQ": "qq",
    "Satori": "satori",
    "Telegram": "telegram",
}

logger = nonebot.logger.opt(colors=True)

for adapter in nonebot.get_adapters():
    if not (module_name := ADAPTER_PLUGINS.get(adapter)):
        continue
    logger.info(f"Loading patchers for adapter <g>{adapter}</>")
    if nonebot.load_plugin(f"{__package__}.{module_name}") is None:
        raise RuntimeError(f"Failed to load the {adapter} patch-event plugin")
