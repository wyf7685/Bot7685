from contextlib import asynccontextmanager
from typing import Never

from nonebot import logger
from nonebot_plugin_alconna import MsgTarget, UniMessage

from src.service.interaction import (
    InteractionBusy,
    InteractionCancelled,
    InteractionLimited,
    InteractionTimeout,
    SessionGuard,
)
from src.service.s3 import (
    S3Config,
    S3ConfigurationConflictError,
    S3ConfigurationError,
    S3ConfigurationInUseError,
    S3ConfigurationSnapshot,
    get_s3_service,
)

_CONFIGURATION_GUARD = SessionGuard()


@asynccontextmanager
async def config_operation(target: MsgTarget):
    if not target.private:
        await UniMessage.text("请在私聊中执行 S3 配置，避免凭据泄漏。").finish()
    try:
        async with _CONFIGURATION_GUARD.acquire():
            yield
    except InteractionBusy:
        await UniMessage.text("已有 S3 配置会话正在进行，请稍后重试。").finish()
    except InteractionCancelled:
        await UniMessage.text("已取消 S3 配置。").finish()
    except InteractionTimeout:
        await UniMessage.text("等待输入超时，已取消 S3 配置。").finish()
    except InteractionLimited:
        await UniMessage.text("输入错误次数过多，已取消 S3 配置。").finish()


async def configured_snapshot() -> tuple[S3ConfigurationSnapshot, S3Config]:
    snapshot = await get_s3_service().configuration_snapshot()
    if snapshot.config is None:
        message = (
            "S3 配置文件不可用，请执行 /s3 config setup。"
            if snapshot.load_error
            else "S3 尚未配置，请执行 /s3 config setup。"
        )
        await UniMessage.text(message).finish()
    return snapshot, snapshot.config


async def replace_configuration(config: S3Config, revision: int) -> int:
    try:
        return await get_s3_service().replace_configuration(
            config,
            expected_revision=revision,
        )
    except S3ConfigurationConflictError:
        await UniMessage.text("S3 配置已被其他操作修改，请重新开始。").finish()
    except S3ConfigurationInUseError:
        await UniMessage.text(
            "当前命名空间仍有临时对象，不能切换 Bucket、Endpoint 或前缀。"
        ).finish()
    except S3ConfigurationError as error:
        await finish_service_error(error)


async def reset_configuration(revision: int) -> int:
    try:
        return await get_s3_service().reset_configuration(expected_revision=revision)
    except S3ConfigurationConflictError:
        await UniMessage.text("S3 配置已被其他操作修改，请重新开始。").finish()
    except S3ConfigurationInUseError:
        await UniMessage.text("仍有临时对象等待清理，不能删除 S3 配置。").finish()
    except S3ConfigurationError as error:
        await finish_service_error(error)


async def finish_service_error(error: S3ConfigurationError) -> Never:
    cause = error.cause or error
    logger.error(f"S3 configuration operation failed: {type(cause).__name__}")
    await UniMessage.text("S3 配置操作失败，原配置保持不变。").finish()


__all__ = [
    "config_operation",
    "configured_snapshot",
    "replace_configuration",
    "reset_configuration",
]
