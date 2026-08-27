from nonebot_plugin_alconna import UniMessage

from src.service.llm import (
    LLMConfigurationError,
    LLMModelSelectionError,
    get_llm_service,
)

from .common import finish_service_error
from .formatting import format_model_list, format_status
from .matcher import model_admin


@model_admin.assign("status")
async def handle_status() -> None:
    snapshot = await get_llm_service().configuration_snapshot()
    await UniMessage.text(format_status(snapshot)).finish()


@model_admin.assign("model.list")
async def handle_model_list() -> None:
    service = get_llm_service()
    try:
        active = await service.get_active_model()
    except LLMConfigurationError as error:
        await finish_service_error(error)
    message = format_model_list(active.alias, service.list_models())
    await UniMessage.text(message).finish()


@model_admin.assign("model.use")
async def handle_model_use(alias: str) -> None:
    try:
        model = await get_llm_service().select_model(alias)
    except LLMModelSelectionError as error:
        await UniMessage.text(str(error)).finish()
    except LLMConfigurationError as error:
        await finish_service_error(error)
    await UniMessage.text(f"已切换至模型：{model.alias}").finish()


__all__ = []
