from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_waiter")
require("src.plugins.cache")

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="kuro",
    description="库洛插件",
    usage="None",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
        "nonebot_plugin_waiter",
    ),
    config=Config,
)

from . import matchers as matchers
from . import schedulers as schedulers
