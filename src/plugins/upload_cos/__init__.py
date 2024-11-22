from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")

from . import matchers as matchers
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="upload_cos",
    description="上传图片到 COS",
    usage="cos上传",
    type="application",
    config=Config,
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

from .exports import upload_from_buffer, upload_from_local, upload_from_url

__all__ = ["upload_from_buffer", "upload_from_local", "upload_from_url"]
