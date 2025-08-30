from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
from . import matcher as matcher
from . import scheduler as scheduler

__plugin_meta__ = PluginMetadata(
    name="WPlace Paint",
    description="WPlace 像素恢复通知",
    usage="见 /wplace --help",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "author": "wyf7685",
    },
)
