import nonebot

from . import common as common

ADAPTER_PLUGINS = {
    "Discord": "discord",
    "Milky": "milky",
    "OneBot V11": "onebot11",
    "Telegram": "telegram",
}

for adapter in nonebot.get_adapters():
    if (module_name := ADAPTER_PLUGINS.get(adapter)) and nonebot.load_plugin(
        f"{__package__}.{module_name}"
    ) is None:
        raise RuntimeError(f"Failed to load the {adapter} group-pipe plugin")
