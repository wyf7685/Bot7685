from nonebot.plugin import PluginMetadata

from . import adapters as adapters
from .patcher import Patcher as Patcher

__plugin_meta__ = PluginMetadata(
    name="patch_event",
    description="Patch Event.get_log_string()",
    usage="None",
    type="application",
    supported_adapters={
        "~onebot.v11",
        "~discord",
        "~qq",
        "~satori",
        "~telegram",
    },
)
