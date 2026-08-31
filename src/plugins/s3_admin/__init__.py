from nonebot.plugin import PluginMetadata, inherit_supported_adapters

__plugin_meta__ = PluginMetadata(
    name="S3 Manager",
    description="管理 Bot 全局 S3 兼容对象存储配置、上传与临时权限",
    usage=(
        "s3 status\ns3 config setup|edit|reset\ns3 permission grant|revoke|list\ns3上传"
    ),
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
    extra={"author": "wyf7685"},
)

from . import permissions as _permissions
from . import setup as _setup
from . import status as _status
from . import upload as _upload
from .matcher import s3_admin as s3_admin
from .matcher import s3_upload as s3_upload

_HANDLER_MODULES = (_permissions, _setup, _status, _upload)

__all__ = ["s3_admin", "s3_upload"]
