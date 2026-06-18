from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from . import matcher as matcher
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="年度报告",
    description="生成聊天年度报告",
    usage=(
        "使用命令 'annual_report [年份]' 或 '年度报告 [年份]' 生成年度报告，"
        "年份可选，默认为当前年份"
    ),
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_chatrecorder",
        "nonebot_plugin_uninfo",
    ),
    extra={"author": "wyf7685"},
)
