from nonebot_plugin_alconna import MsgTarget, UniMessage

from src.service.interaction import confirm
from src.service.llm import LLMConfig, get_llm_service

from .common import config_operation, replace_configuration, reset_configuration
from .formatting import format_configuration
from .forms import (
    EndpointOptionError,
    ModelOptionError,
    ask_alias,
    ask_endpoint,
    ask_model,
)
from .matcher import model_admin


@model_admin.assign("config.setup")
async def handle_setup(target: MsgTarget) -> None:
    async with config_operation(target):
        snapshot = await get_llm_service().configuration_snapshot()
        if snapshot.config is not None:
            await UniMessage.text(
                "LLM 已配置。请使用 endpoint/model 编辑命令，或先执行 reset。"
            ).finish()

        endpoint_alias = await ask_alias("请输入第一个 endpoint 别名", {})
        try:
            endpoint = await ask_endpoint(alias=endpoint_alias)
        except EndpointOptionError as error:
            await UniMessage.text(str(error)).finish()
        model_alias = await ask_alias("请输入第一个模型别名", {})
        try:
            model = await ask_model(
                alias=model_alias,
                endpoints={endpoint_alias: endpoint},
                force_selectable=True,
            )
        except ModelOptionError as error:
            await UniMessage.text(str(error)).finish()
        config = LLMConfig(
            active_model=model_alias,
            endpoints={endpoint_alias: endpoint},
            models={model_alias: model},
        )
        summary = format_configuration(config)
        if not await confirm(f"将保存以下 LLM 配置：\n\n{summary}\n\n确认保存吗？"):
            await UniMessage.text("未保存 LLM 配置。").finish()
        await replace_configuration(config, snapshot.revision)
        await UniMessage.text("LLM 配置已保存并立即生效。").finish()


@model_admin.assign("config.reset")
async def handle_reset(target: MsgTarget) -> None:
    async with config_operation(target):
        snapshot = await get_llm_service().configuration_snapshot()
        if snapshot.config is None and not snapshot.load_error:
            await UniMessage.text("LLM 当前未配置。").finish()
        if not await confirm("将删除全部 LLM 配置并停止接受新的 LLM 请求，确认吗？"):
            await UniMessage.text("未重置 LLM 配置。").finish()
        await reset_configuration(snapshot.revision)
        await UniMessage.text("LLM 配置已删除。").finish()


__all__ = []
