from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .config import RootConfig

__plugin_meta__ = PluginMetadata(
    name="zssm",
    description="群聊上下文增强的工具调用式大语言模型助手",
    usage="zssm [内容]",
    type="application",
    config=RootConfig,
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_orm",
        "nonebot_plugin_chatrecorder",
        "nonebot_plugin_uninfo",
    ),
    extra={"author": "wyf7685"},
)

from . import command as command
from . import handler as handler

__all__ = ["command", "handler"]
