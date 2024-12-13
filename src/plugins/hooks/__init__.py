import importlib

from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="hooks",
    description="set bot hooks",
    usage="None",
    type="application",
)


def __init() -> None:
    for name in "clean_pycache", "hook_memes", "meow":
        importlib.import_module(f"{__name__}.{name}")


__init()
