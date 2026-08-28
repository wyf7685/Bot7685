from contextlib import asynccontextmanager
from typing import Never

from nonebot import logger
from nonebot_plugin_alconna import MsgTarget, UniMessage

from src.service.llm import (
    LLMConfig,
    LLMConfigurationConflictError,
    LLMConfigurationError,
    LLMConfigurationSnapshot,
    get_llm_service,
)

from .interaction import (
    InteractionBusy,
    InteractionCancelled,
    InteractionLimited,
    InteractionTimeout,
    configuration_session,
)


@asynccontextmanager
async def config_operation(target: MsgTarget):
    if not target.private:
        await UniMessage.text("请在私聊中执行 LLM 配置，避免凭据泄漏。").finish()
    try:
        async with configuration_session():
            yield
    except InteractionBusy:
        await UniMessage.text("已有 LLM 配置会话正在进行，请稍后重试。").finish()
    except InteractionCancelled:
        await UniMessage.text("已取消 LLM 配置。").finish()
    except InteractionTimeout:
        await UniMessage.text("等待输入超时，已取消 LLM 配置。").finish()
    except InteractionLimited:
        await UniMessage.text("输入错误次数过多，已取消 LLM 配置。").finish()


async def configured_snapshot() -> tuple[LLMConfigurationSnapshot, LLMConfig]:
    snapshot = await get_llm_service().configuration_snapshot()
    if snapshot.config is None:
        message = (
            "LLM 配置文件不可用。请在私聊执行 /llm config setup 重新配置。"
            if snapshot.load_error
            else "LLM 尚未配置。请在私聊执行 /llm config setup。"
        )
        await UniMessage.text(message).finish()
    return snapshot, snapshot.config


async def replace_configuration(config: LLMConfig, expected_revision: int) -> int:
    try:
        return await get_llm_service().replace_configuration(
            config,
            expected_revision=expected_revision,
        )
    except LLMConfigurationConflictError:
        await UniMessage.text("LLM 配置已被其他操作修改，请重新开始。").finish()
    except LLMConfigurationError as error:
        await _finish_service_error(error)


async def reset_configuration(expected_revision: int) -> int:
    try:
        return await get_llm_service().reset_configuration(
            expected_revision=expected_revision
        )
    except LLMConfigurationConflictError:
        await UniMessage.text("LLM 配置已被其他操作修改，请重新开始。").finish()
    except LLMConfigurationError as error:
        await _finish_service_error(error)


async def finish_service_error(error: LLMConfigurationError) -> Never:
    await _finish_service_error(error)


async def _finish_service_error(error: LLMConfigurationError) -> Never:
    cause = error.cause or error
    logger.error(f"LLM configuration operation failed: {type(cause).__name__}")
    await UniMessage.text("LLM 配置操作失败，原配置保持不变。").finish()


__all__ = [
    "config_operation",
    "configured_snapshot",
    "finish_service_error",
    "replace_configuration",
    "reset_configuration",
]
