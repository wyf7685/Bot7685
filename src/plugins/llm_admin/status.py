from nonebot.adapters import Bot
from nonebot_plugin_alconna import CustomNode, UniMessage

from src.service.llm import (
    LLMConfigurationError,
    LLMModelSelectionError,
    get_llm_service,
)

from .common import configured_snapshot, finish_service_error
from .formatting import format_endpoint, format_model, format_model_list, format_status
from .matcher import model_admin


@model_admin.assign("status")
async def handle_status(bot: Bot) -> None:
    snapshot = await get_llm_service().configuration_snapshot()
    if snapshot.config is None:
        await UniMessage.text(format_status(snapshot)).finish()

    config = snapshot.config
    nodes = [
        CustomNode(
            uid=bot.self_id,
            name="LLM 状态 - 概览",
            content=f"活动模型：{config.active_model}",
        )
    ]
    nodes.extend(
        CustomNode(
            uid=bot.self_id,
            name=f"LLM Endpoint - {alias}",
            content=format_endpoint(alias, endpoint),
        )
        for alias, endpoint in sorted(config.endpoints.items())
    )
    nodes.extend(
        CustomNode(
            uid=bot.self_id,
            name=f"LLM 模型 - {alias}",
            content=format_model(alias, model, active=alias == config.active_model),
        )
        for alias, model in sorted(config.models.items())
    )
    await UniMessage.reference(*nodes).finish()


@model_admin.assign("model.list")
async def handle_model_list() -> None:
    service = get_llm_service()
    _, config = await configured_snapshot()
    message = format_model_list(config.active_model, service.list_models())
    await UniMessage.text(message).finish()


@model_admin.assign("model.use")
async def handle_model_use(alias: str) -> None:
    await configured_snapshot()
    try:
        model = await get_llm_service().select_model(alias)
    except LLMModelSelectionError as error:
        await UniMessage.text(str(error)).finish()
    except LLMConfigurationError as error:
        await finish_service_error(error)
    await UniMessage.text(f"已切换至模型：{model.alias}").finish()


__all__ = []
