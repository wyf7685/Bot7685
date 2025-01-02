from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("nonebot_plugin_uninfo")

__plugin_meta__ = PluginMetadata(
    name="trusted",
    description="Manage trusted user or group",
    usage="trust -h",
    type="library",
)


from .trust_data import TrustedUser as TrustedUser

__all__ = ["TrustedUser"]
