from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Never

from arclet.alconna import Alconna, AllParam, Args, Subcommand
from nonebot import logger
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    AlconnaMatch,
    Match,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyRecordExtension

from .config import ZssmConfig
from .state import ModelSelectionError, active_model_store, get_zssm_config

if TYPE_CHECKING:
    from src.service.llm.config import LLMConfig
    from src.service.llm.service import LLMService


type ParsedContent = Annotated[Match[UniMessage], AlconnaMatch("content")]

matcher = on_alconna(
    Alconna("zssm", Args["content?", AllParam]),
    extensions=[ReplyRecordExtension()],
    use_cmd_start=True,
    block=True,
)

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


def _load_model_context() -> tuple[ZssmConfig, LLMConfig, LLMService]:
    from src.service.llm.config import service_config
    from src.service.llm.service import get_llm_service

    return get_zssm_config(), service_config, get_llm_service()


async def _finish_configuration_error() -> Never:
    logger.warning("ZSSM command configuration is unavailable.")
    await UniMessage.text("ZSSM configuration is unavailable.").finish()


def _model_line(
    alias: str,
    model_id: str,
    *,
    tools: bool,
    vision: bool,
    active: bool,
    selectable: bool,
    fallback_only: bool,
) -> str:
    states: list[str] = []
    if active:
        states.append("active")
    if selectable:
        states.append("selectable")
    if fallback_only:
        states.append("fallback-only")
    if not states:
        states.append("not-selectable")
    return (
        f"- {alias!r}: model={model_id!r}; tools={"yes" if tools else "no"}; "
        f"vision={"yes" if vision else "no"}; status={", ".join(states)}"
    )


@model_admin.assign("model.list")
async def _handle_model_list() -> None:
    try:
        config, llm_config, service = _load_model_context()
    except Exception:
        await _finish_configuration_error()

    try:
        active = await active_model_store.snapshot(config, llm_config.models)
        lines = ["ZSSM models:"]
        for alias in sorted(llm_config.models):
            handle = service.runtime.resolve(alias)
            lines.append(
                _model_line(
                    alias,
                    handle.model_id,
                    tools=handle.capabilities.tools,
                    vision=handle.capabilities.vision,
                    active=alias == active.active_model,
                    selectable=alias in config.selectable_models,
                    fallback_only=alias == config.vision_model,
                )
            )
    except Exception:
        await _finish_configuration_error()

    await UniMessage.text("\n".join(lines)).finish()


@model_admin.assign("model.use")
async def _handle_model_use(alias: str) -> None:
    try:
        config, llm_config, service = _load_model_context()
    except Exception:
        await _finish_configuration_error()

    normalized = alias.strip()
    try:
        if normalized in llm_config.models:
            service.runtime.resolve(normalized)
        state = await active_model_store.select(
            normalized,
            config,
            llm_config.models,
        )
    except ModelSelectionError as error:
        await UniMessage.text(str(error)).finish()
    except Exception:
        await _finish_configuration_error()

    await UniMessage.text(f"Active model set to {state.active_model!r}.").finish()


__all__ = ["ParsedContent", "matcher", "model_admin"]
