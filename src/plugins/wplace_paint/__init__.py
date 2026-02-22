from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_uninfo")
require("nonebot_plugin_user")
require("nonebot_plugin_waiter")
require("src.plugins.cache")
require("src.plugins.group_pipe")
from . import command as command
from . import scheduler as scheduler

__plugin_meta__ = PluginMetadata(
    name="WPlace Paint",
    description="WPlace 辅助工具",
    usage="见 /wplace --help",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={
        "author": "wyf7685",
    },
)
