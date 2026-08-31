from nonebot_plugin_alconna import MsgTarget, UniMessage
from pydantic import ValidationError

from src.service.s3 import get_s3_service

from .common import config_operation, replace_configuration, reset_configuration
from .formatting import format_config
from .forms import ask_s3_config
from .interaction import confirm
from .matcher import s3_admin


@s3_admin.assign("config.setup")
async def handle_setup(target: MsgTarget) -> None:
    async with config_operation(target):
        snapshot = await get_s3_service().configuration_snapshot()
        if snapshot.config is not None:
            await UniMessage.text(
                "S3 已配置，请使用 /s3 config edit 或先 reset。"
            ).finish()
        try:
            config = await ask_s3_config()
        except ValidationError:
            await UniMessage.text("S3 配置校验失败，未保存。").finish()
        if not await confirm(f"将保存以下 S3 配置：\n\n{format_config(config)}"):
            await UniMessage.text("未保存 S3 配置。").finish()
        await replace_configuration(config, snapshot.revision)
        await UniMessage.text("S3 配置已保存并立即生效。").finish()


@s3_admin.assign("config.edit")
async def handle_edit(target: MsgTarget) -> None:
    async with config_operation(target):
        snapshot = await get_s3_service().configuration_snapshot()
        if snapshot.config is None:
            await UniMessage.text("S3 尚未配置，请先执行 /s3 config setup。").finish()
        try:
            config = await ask_s3_config(snapshot.config)
        except ValidationError:
            await UniMessage.text("S3 配置校验失败，未保存。").finish()
        if not await confirm(f"将更新为以下 S3 配置：\n\n{format_config(config)}"):
            await UniMessage.text("未更新 S3 配置。").finish()
        await replace_configuration(config, snapshot.revision)
        await UniMessage.text("S3 配置已更新并立即生效。").finish()


@s3_admin.assign("config.reset")
async def handle_reset(target: MsgTarget) -> None:
    async with config_operation(target):
        snapshot = await get_s3_service().configuration_snapshot()
        if snapshot.config is None and not snapshot.load_error:
            await UniMessage.text("S3 当前未配置。").finish()
        if not await confirm("将删除 S3 配置并停止接受新请求，确认吗？"):
            await UniMessage.text("未删除 S3 配置。").finish()
        await reset_configuration(snapshot.revision)
        await UniMessage.text("S3 配置已删除。").finish()


__all__ = []
