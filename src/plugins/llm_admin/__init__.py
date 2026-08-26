from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")

__plugin_meta__ = PluginMetadata(
    name="LLM Model Manager",
    description="管理 Bot 全局 LLM 活动模型",
    usage="llm model list\nllm model use <alias>",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"author": "wyf7685"},
)

from .command import model_admin as model_admin

__all__ = ["model_admin"]
