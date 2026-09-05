from nonebot_plugin_alconna import MsgTarget, UniMessage

from src.service.interaction import confirm
from src.service.llm import LLMConfig

from .common import config_operation, configured_snapshot, replace_configuration
from .formatting import format_endpoint
from .forms import ask_endpoint
from .matcher import model_admin


@model_admin.assign("config.endpoint.list")
async def handle_endpoint_list() -> None:
    _, config = await configured_snapshot()
    message = "Endpoints:\n" + "\n".join(
        format_endpoint(alias, endpoint)
        for alias, endpoint in sorted(config.endpoints.items())
    )
    await UniMessage.text(message).finish()


@model_admin.assign("config.endpoint.add")
async def handle_endpoint_add(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        if not alias or alias in config.endpoints:
            await UniMessage.text("Endpoint 别名为空或已存在。").finish()
        endpoint = await ask_endpoint(alias=alias)
        if not await confirm(
            f"确认添加 endpoint {alias!r}？\n{format_endpoint(alias, endpoint)}"
        ):
            await UniMessage.text("未添加 endpoint。").finish()
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints={**config.endpoints, alias: endpoint},
            models=dict(config.models),
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已添加 endpoint：{alias}").finish()


@model_admin.assign("config.endpoint.edit")
async def handle_endpoint_edit(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        endpoint = config.endpoints.get(alias)
        if endpoint is None:
            await UniMessage.text("未找到该 endpoint。").finish()
        updated = await ask_endpoint(alias=alias, existing=endpoint)
        if not await confirm(
            f"确认更新 endpoint {alias!r}？\n{format_endpoint(alias, updated)}"
        ):
            await UniMessage.text("未更新 endpoint。").finish()
        endpoints = dict(config.endpoints)
        endpoints[alias] = updated
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints=endpoints,
            models=dict(config.models),
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已更新 endpoint：{alias}").finish()


@model_admin.assign("config.endpoint.remove")
async def handle_endpoint_remove(target: MsgTarget, alias: str) -> None:
    async with config_operation(target):
        snapshot, config = await configured_snapshot()
        alias = alias.strip()
        if alias not in config.endpoints:
            await UniMessage.text("未找到该 endpoint。").finish()
        referenced = sorted(
            model_alias
            for model_alias, model in config.models.items()
            if model.endpoint == alias
        )
        if referenced:
            await UniMessage.text(
                "该 endpoint 仍被以下模型引用：" + ", ".join(referenced)
            ).finish()
        if not await confirm(f"确认删除 endpoint {alias!r}？"):
            await UniMessage.text("未删除 endpoint。").finish()
        endpoints = dict(config.endpoints)
        del endpoints[alias]
        candidate = LLMConfig(
            active_model=config.active_model,
            endpoints=endpoints,
            models=dict(config.models),
        )
        await replace_configuration(candidate, snapshot.revision)
        await UniMessage.text(f"已删除 endpoint：{alias}").finish()


__all__ = []
