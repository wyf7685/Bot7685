from __future__ import annotations

from typing import Never

from arclet.alconna import Alconna, Args, Subcommand
from nonebot import logger
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import UniMessage, on_alconna

from src.service.llm import LLMModelSelectionError, ModelInfo, get_llm_service

model_admin = on_alconna(
    Alconna(
        "llm",
        Subcommand(
            "model",
            Subcommand("list"),
            Subcommand("use", Args["alias", str]),
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
    block=True,
)


def _format_model_list(active_alias: str, models: tuple[ModelInfo, ...]) -> str:
    selectable = sorted(
        (model for model in models if model.selectable),
        key=lambda model: (model.alias != active_alias, model.alias),
    )
    unavailable = sorted(
        (model for model in models if not model.selectable),
        key=lambda model: model.alias,
    )

    lines = ["可切换模型："]
    lines.extend(
        f"- {model.alias}{"（当前）" if model.alias == active_alias else ""}"
        for model in selectable
    )
    if unavailable:
        lines.extend(("", "不可切换模型："))
        lines.extend(f"- {model.alias}" for model in unavailable)
    return "\n".join(lines)


async def _finish_configuration_error() -> Never:
    logger.exception("LLM model command configuration is unavailable.")
    await UniMessage.text("LLM 配置不可用。").finish()


@model_admin.assign("model.list")
async def _handle_model_list() -> None:
    try:
        service = get_llm_service()
        active = await service.get_active_model()
        message = _format_model_list(active.alias, service.list_models())
    except Exception:
        await _finish_configuration_error()

    await UniMessage.text(message).finish()


@model_admin.assign("model.use")
async def _handle_model_use(alias: str) -> None:
    try:
        model = await get_llm_service().select_model(alias)
    except LLMModelSelectionError as error:
        await UniMessage.text(str(error)).finish()
    except Exception:
        await _finish_configuration_error()

    await UniMessage.text(f"已切换至模型：{model.alias}").finish()


__all__ = ["model_admin"]
