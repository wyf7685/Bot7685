from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from . import command as command

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
