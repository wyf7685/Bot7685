"""群聊日常分析插件。

移植自 AstrBot 插件 astrbot_plugin_qq_group_daily_analysis v4.10.5
原作者: SXP-Simon (Helian Nuits)
原仓库: https://github.com/SXP-Simon/astrbot_plugin_qq_group_daily_analysis
许可协议: MIT License

本插件保留了原项目的领域模型、LLM 分析流程、HTML 模板和提示词
基础设施层替换为 NoneBot2 生态组件（chatrecorder / alconna / uninfo / htmlrender / orm）
"""

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_localstore")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
require("src.service.cache")
require("src.service.llm")

from . import matchers as matchers
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="群聊日常分析",
    description="基于群聊记录生成精美的日常分析报告，包含话题总结、用户画像、金句提取、聊天质量评估",
    usage="使用命令 '群分析 [天数]' 生成当日群聊分析报告",
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_chatrecorder",
        "nonebot_plugin_uninfo",
    ),
    extra={"author": "wyf7685"},
)
