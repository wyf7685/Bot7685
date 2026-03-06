from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_waiter")
from . import matchers as matchers
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Artifact Fetch",
    description="A plugin to fetch GitHub Actions artifacts.",
    usage="<TODO>",
    type="application",
    config=Config,
    supported_adapters={"~milky"},
)
