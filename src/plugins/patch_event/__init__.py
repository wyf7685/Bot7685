from nonebot.plugin import PluginMetadata

from . import adapters as adapters
from .patcher import dispose as dispose
from .patcher import patcher as patcher

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
