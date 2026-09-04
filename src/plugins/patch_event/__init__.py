from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="patch_event",
    description="Patch Event.get_log_string()",
    usage="None",
    type="application",
    config=Config,
    supported_adapters={
        "~discord",
        "~feishu",
        "~github",
        "~milky",
        "~onebot.v11",
        "~qq",
        "~satori",
        "~telegram",
    },
)

from . import adapters as adapters
from .patcher import patcher as patcher
