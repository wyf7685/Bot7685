from nonebot import logger
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from src.highlight import Highlight

from .config import Config, plugin_config

__plugin_meta__ = PluginMetadata(
    name="Screen Detector",
    description="识别指定群聊中的屏幕实拍图片，并支持人工反馈与检测数据打包",
    usage=(
        "自动检测 screen.enabled_scenes 指定群聊中的图片\n"
        "detector package <duration>\n"
        "detector subscribe|unsubscribe"
    ),
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
    extra={"author": "wyf7685"},
)

from . import command as command
from . import database as database
from . import detect as detect
from . import reaction as reaction
from . import scheduler as scheduler

logger.debug(
    "Screen Detector plugin loaded "
    f"(API configured: {Highlight.apply(bool(plugin_config.api_base_url))})"
)
