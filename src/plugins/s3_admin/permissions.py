from nonebot.adapters import Bot
from nonebot_plugin_alconna import At, Match, UniMessage
from nonebot_plugin_apscheduler import scheduler

from .matcher import s3_admin
from .permission_store import (
    grant_permission,
    list_permissions,
    remove_expired_permissions,
    revoke_permission,
)


def _identity(bot: Bot, user_id: str) -> str:
    return f"{bot.type}:{user_id}"


@s3_admin.assign("permission.grant")
async def handle_grant(bot: Bot, target: At, seconds: Match[int]) -> None:
    expires_in = seconds.result if seconds.available else 60
    if expires_in <= 0:
        await UniMessage.text("授权时长必须大于 0 秒。").finish()
    await grant_permission(_identity(bot, target.target), expires_in)
    await (
        UniMessage.text("已临时授权 ")
        .at(target.target)
        .text(f"：{expires_in}s")
        .finish()
    )


@s3_admin.assign("permission.revoke")
async def handle_revoke(bot: Bot, target: At) -> None:
    removed = await revoke_permission(_identity(bot, target.target))
    message = "已撤销上传权限" if removed else "该用户没有有效上传权限"
    await UniMessage.text(message + " ").at(target.target).finish()


@s3_admin.assign("permission.list")
async def handle_list(bot: Bot) -> None:
    permissions = await list_permissions(bot.type)
    if not permissions:
        await UniMessage.text("当前适配器没有临时上传权限。").finish()
    lines = [f"{user_id}: {remaining}s" for user_id, remaining in permissions]
    await UniMessage.text("临时上传权限\n" + "\n".join(lines)).finish()


@scheduler.scheduled_job(
    "interval",
    minutes=10,
    id="s3_upload_permission_cleanup",
    max_instances=1,
    coalesce=True,
)
async def cleanup_permissions() -> None:
    await remove_expired_permissions()


__all__ = []
