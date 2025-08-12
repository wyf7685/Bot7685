from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_uninfo")

from . import hooks as hooks
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="monitor",
    description="群聊内容监控插件",
    usage="监控群聊内容，检测敏感话题",
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_chatrecorder",
        "nonebot_plugin_uninfo",
    ),
)
