from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

requirements = [
    "nonebot_plugin_alconna",
    "nonebot_plugin_apscheduler",
    "nonebot_plugin_chatrecorder",
    "nonebot_plugin_htmlrender",
    "nonebot_plugin_orm",
    "nonebot_plugin_uninfo",
]

[require(req) for req in requirements]
require("src.plugins.trusted")

from . import matcher as matcher
from . import scheduler as scheduler
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Talk Stats",
    description="群聊活跃度统计",
    usage="talk_stats -h",
    type="application",
    # homepage="",
    config=Config,
    supported_adapters=inherit_supported_adapters(*requirements),
)
