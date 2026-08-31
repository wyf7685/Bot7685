from arclet.alconna import Alconna, Args, CommandMeta, Subcommand
from nonebot import on_startswith
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import At, on_alconna

from .depends import ALLOW_UPLOAD

s3_admin = on_alconna(
    Alconna(
        "s3",
        Subcommand("status", help_text="查看 S3 配置与连接状态"),
        Subcommand(
            "config",
            Subcommand("setup", help_text="通过私聊向导创建配置"),
            Subcommand("edit", help_text="通过私聊向导编辑配置"),
            Subcommand("reset", help_text="删除 S3 配置"),
            help_text="管理 S3 服务配置",
        ),
        Subcommand(
            "permission",
            Subcommand(
                "grant",
                Args["target", At]["seconds?", int],
                help_text="临时授予图片上传权限",
            ),
            Subcommand(
                "revoke",
                Args["target", At],
                help_text="撤销图片上传权限",
            ),
            Subcommand("list", help_text="列出当前适配器的临时权限"),
            help_text="管理临时上传权限",
        ),
        meta=CommandMeta(
            description="管理 Bot 的 S3 兼容对象存储服务",
            usage=(
                "s3 status\ns3 config setup|edit|reset\ns3 permission grant|revoke|list"
            ),
            author="wyf7685",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)

s3_upload = on_startswith("s3上传", permission=ALLOW_UPLOAD, block=True)

__all__ = ["s3_admin", "s3_upload"]
