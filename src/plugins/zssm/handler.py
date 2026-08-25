from __future__ import annotations

import asyncio
from typing import Never

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, MsgId, UniMessage, UniMsg, image_fetch
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyRecordExtension
from nonebot_plugin_uninfo import Uninfo

from src.service.llm import LLMServiceError, get_llm_service

from .command import ParsedContent, matcher
from .contracts import RenderFailure, RenderFailureCategory
from .input import EmptyInputError, ImageLimitError, UnsupportedInputError
from .orchestrator import AllImagesFailedError, run_zssm
from .render import (
    ReferenceSendError,
    build_reference_nodes,
    render_error,
    send_reference,
)
from .state import get_zssm_config


async def _finish_failure(
    category: RenderFailureCategory,
    *,
    cause: type[BaseException] | None = None,
) -> Never:
    logger.warning(
        "ZSSM request failed: category={} cause={}",
        category.value,
        cause.__name__ if cause is not None else "none",
    )
    await render_error(
        RenderFailure(category=category, message=category.value)
    ).finish()


def _quoted_message(
    reply_extension: ReplyRecordExtension,
    message_id: str,
    bot: Bot,
) -> UniMessage | None:
    reply = reply_extension.get_reply(message_id)
    if reply is None or reply.msg is None:
        return None
    if isinstance(reply.msg, UniMessage):
        return reply.msg.copy()
    if isinstance(reply.msg, str):
        return UniMessage.text(reply.msg)
    return UniMessage.of(reply.msg, bot=bot).copy()


@matcher.handle()
async def _handle_zssm(
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
    current: UniMsg,
    content: ParsedContent,
    message_id: MsgId,
    reply_extension: ReplyRecordExtension,
) -> None:
    current_copy = current.copy()
    try:
        quoted_copy = _quoted_message(reply_extension, message_id, bot)
        content_copy = content.result.copy() if content.available else UniMessage()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await _finish_failure(
            RenderFailureCategory.UNSUPPORTED_INPUT,
            cause=type(error),
        )

    try:
        config = get_zssm_config()
        service = get_llm_service()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await _finish_failure(
            RenderFailureCategory.CONFIGURATION,
            cause=type(error),
        )

    async def fetch_adapter_image(image: Image) -> bytes | None:
        return await image_fetch(event, bot, state, image)

    try:
        model = await run_zssm(
            bot=bot,
            session=session,
            current=current_copy,
            content=content_copy,
            quoted=quoted_copy,
            config=config,
            service=service,
            adapter_image_fetcher=fetch_adapter_image,
        )
    except asyncio.CancelledError:
        raise
    except EmptyInputError as error:
        await _finish_failure(RenderFailureCategory.EMPTY_INPUT, cause=type(error))
    except UnsupportedInputError as error:
        await _finish_failure(
            RenderFailureCategory.UNSUPPORTED_INPUT,
            cause=type(error),
        )
    except (ImageLimitError, AllImagesFailedError) as error:
        await _finish_failure(RenderFailureCategory.IMAGE, cause=type(error))
    except LLMServiceError as error:
        logger.warning(
            "ZSSM agent failed: category={} cause={}",
            error.category.value,
            type(error.cause).__name__
            if error.cause is not None
            else type(error).__name__,
        )
        await render_error(error).finish()
    except Exception as error:
        await _finish_failure(RenderFailureCategory.PROVIDER, cause=type(error))

    try:
        nodes = build_reference_nodes(
            model,
            bot_uid=str(bot.self_id),
            config=config.rendering,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await _finish_failure(RenderFailureCategory.RENDER, cause=type(error))

    try:
        await send_reference(nodes)
    except asyncio.CancelledError:
        raise
    except ReferenceSendError as error:
        await _finish_failure(RenderFailureCategory.RENDER, cause=type(error))


__all__ = ["_handle_zssm"]
