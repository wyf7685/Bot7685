from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")


__plugin_meta__ = PluginMetadata(
    name="upload_cos",
    description="上传图片到 COS",
    usage="cos上传",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)
