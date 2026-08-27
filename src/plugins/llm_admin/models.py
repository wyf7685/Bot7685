from nonebot_plugin_alconna import MsgTarget, UniMessage

from src.service.llm import LLMConfig

from .common import config_operation, configured_snapshot, replace_configuration
from .formatting import format_model
from .forms import ask_model
from .interaction import confirm
from .matcher import model_admin


@model_admin.assign("config.model.add")
async def handle_model_add(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        if not alias or alias in config.models:
            await UniMessage.text("模型别名为空或已存在。").finish()
        model = await ask_model(alias=alias, endpoints=config.endpoints)
        if not await confirm(
            f"确认添加模型 {alias!r}？\n{format_model(alias, model, active=False)}"
        ):
            await UniMessage.text("未添加模型。").finish()
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints=dict(config.endpoints),
            models={**config.models, alias: model},
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已添加模型：{alias}").finish()


@model_admin.assign("config.model.edit")
async def handle_model_edit(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        model = config.models.get(alias)
        if model is None:
            await UniMessage.text("未找到该模型。").finish()
        updated = await ask_model(
            alias=alias,
            endpoints=config.endpoints,
            existing=model,
            force_selectable=alias == config.active_model,
        )
        if not await confirm(
            f"确认更新模型 {alias!r}？\n"
            f"{format_model(alias, updated, active=alias == config.active_model)}"
        ):
            await UniMessage.text("未更新模型。").finish()
        models = dict(config.models)
        models[alias] = updated
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints=dict(config.endpoints),
            models=models,
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已更新模型：{alias}").finish()


@model_admin.assign("config.model.remove")
async def handle_model_remove(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        if alias not in config.models:
            await UniMessage.text("未找到该模型。").finish()
        if alias == config.active_model:
            await UniMessage.text("不能删除当前活动模型，请先切换模型。").finish()
        if len(config.models) == 1:
            await UniMessage.text(
                "不能删除最后一个模型；如需清空请执行 reset。"
            ).finish()
        if not await confirm(f"确认删除模型 {alias!r}？"):
            await UniMessage.text("未删除模型。").finish()
        models = dict(config.models)
        del models[alias]
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints=dict(config.endpoints),
            models=models,
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已删除模型：{alias}").finish()


__all__ = []
