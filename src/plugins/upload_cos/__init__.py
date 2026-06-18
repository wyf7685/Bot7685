from nonebot.plugin import PluginMetadata, inherit_supported_adapters

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

from .exports import upload_cos

__all__ = ["upload_cos"]
