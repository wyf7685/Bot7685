import asyncio
import secrets
from time import perf_counter
from typing import Never

from nonebot.adapters import Bot, Event
from nonebot.typing import T_State
from nonebot_plugin_alconna import Image, MsgId, UniMessage, UniMsg, image_fetch
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyRecordExtension
from nonebot_plugin_uninfo import Uninfo

from src.service.llm import LLMCapabilityError, LLMServiceError, get_llm_service

from .command import ParsedContent, matcher
from .config import get_zssm_config
from .contracts import RenderFailure, RenderFailureCategory
from .forward import ForwardFetchError, ForwardLimitError, ForwardUnsupportedError
from .input import EmptyInputError, UnsupportedInputError
from .log import cause_name, current_run_id, log_event, safe_log_text
from .orchestrator import AllImagesFailedError, run_zssm
from .reaction import zssm_reaction_timeline
from .render import (
    ReferenceSendError,
    build_reference_nodes,
    render_error,
    send_reference,
)


async def _finish_failure(
    category: RenderFailureCategory,
    *,
    stage: str,
    request_started: float,
    cause: BaseException | None = None,
) -> Never:
    log_event(
        "WARNING",
        "ZSSM",
        f"<r><b>request failed</b></> | stage=<y>{safe_log_text(stage)}</> "
        f"category=<y>{category.value}</> "
        f"cause=<r>{safe_log_text(repr(cause) if cause is not None else "none")}</> "
        f"elapsed=<c>{(perf_counter() - request_started) * 1000:.1f}ms</>",
    )
    await render_error(
        RenderFailure(category=category, message=category.value)
    ).finish()


async def _finish_llm_failure(
    error: LLMServiceError,
    *,
    request_started: float,
) -> Never:
    capability = (
        f" capability=<y>{safe_log_text(error.capability.value)}</>"
        if isinstance(error, LLMCapabilityError)
        else ""
    )
    log_event(
        "WARNING",
        "ZSSM",
        f"<r><b>request failed</b></> | stage=<y>agent</> "
        f"category=<y>{error.category.value}</>{capability} "
        f"cause=<r>{safe_log_text(cause_name(error))}</> "
        f"elapsed=<c>{(perf_counter() - request_started) * 1000:.1f}ms</>",
    )
    await render_error(error).finish()


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
    model_alias: str | None = None,
) -> None:
    with current_run_id.set(secrets.token_hex(8)):
        request_started = perf_counter()
        log_event(
            "INFO",
            "ZSSM",
            f"<b>request accepted</> | segments=<c>{len(current)}</> "
            f"content=<y>{str(content.available).lower()}</> "
            f"model=<g>{safe_log_text(model_alias or "$active")}</>",
        )
        try:
            async with zssm_reaction_timeline(bot, event):
                await _execute_zssm(
                    bot=bot,
                    event=event,
                    state=state,
                    session=session,
                    current=current,
                    content=content,
                    model_alias=model_alias,
                    message_id=message_id,
                    reply_extension=reply_extension,
                    request_started=request_started,
                )
        except asyncio.CancelledError:
            log_event(
                "INFO",
                "ZSSM",
                f"<y>request cancelled</> | "
                f"elapsed=<c>{(perf_counter() - request_started) * 1000:.1f}ms</>",
            )
            raise


async def _execute_zssm(
    bot: Bot,
    event: Event,
    state: T_State,
    session: Uninfo,
    current: UniMsg,
    content: ParsedContent,
    model_alias: str | None,
    message_id: MsgId,
    reply_extension: ReplyRecordExtension,
    request_started: float,
) -> None:
    async def finish_failure(
        category: RenderFailureCategory,
        stage: str,
        error: BaseException,
    ) -> Never:
        await _finish_failure(
            category,
            stage=stage,
            request_started=request_started,
            cause=error,
        )

    current_copy = current.copy()
    try:
        quoted_copy = _quoted_message(reply_extension, message_id, bot)
        content_copy = content.result.copy() if content.available else UniMessage()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await finish_failure(
            RenderFailureCategory.UNSUPPORTED_INPUT,
            "input_snapshot",
            error,
        )

    try:
        config = get_zssm_config()
        service = get_llm_service()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await finish_failure(
            RenderFailureCategory.CONFIGURATION,
            "configuration",
            error,
        )

    async def fetch_adapter_image(image: Image) -> bytes | None:
        return await image_fetch(event, bot, state, image)

    try:
        model = await run_zssm(
            bot=bot,
            event=event,
            session=session,
            current=current_copy,
            content=content_copy,
            quoted=quoted_copy,
            config=config,
            service=service,
            model_alias=model_alias,
            adapter_image_fetcher=fetch_adapter_image,
        )
    except asyncio.CancelledError:
        raise
    except ForwardLimitError as error:
        await finish_failure(RenderFailureCategory.LIMITS, "forward", error)
    except ForwardFetchError as error:
        await finish_failure(RenderFailureCategory.FORWARD, "forward", error)
    except ForwardUnsupportedError as error:
        await finish_failure(
            RenderFailureCategory.UNSUPPORTED_INPUT,
            "forward",
            error,
        )
    except EmptyInputError as error:
        await finish_failure(RenderFailureCategory.EMPTY_INPUT, "input", error)
    except UnsupportedInputError as error:
        await finish_failure(
            RenderFailureCategory.UNSUPPORTED_INPUT,
            "input",
            error,
        )
    except AllImagesFailedError as error:
        await finish_failure(RenderFailureCategory.IMAGE, "image", error)
    except LLMServiceError as error:
        await _finish_llm_failure(
            error,
            request_started=request_started,
        )
    except Exception as error:
        await finish_failure(RenderFailureCategory.PROVIDER, "agent", error)

    render_started = perf_counter()
    try:
        nodes = build_reference_nodes(
            model,
            bot_uid=str(bot.self_id),
            config=config.rendering,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        await finish_failure(RenderFailureCategory.RENDER, "render", error)

    log_event(
        "INFO",
        "ZSSM::Render",
        f"<b>reference built</> | nodes=<c>{len(nodes)}</> "
        f"sources=<c>{len(model.sources)}</> trace_entries=<c>{len(model.trace)}</> "
        f"elapsed=<c>{(perf_counter() - render_started) * 1000:.1f}ms</>",
    )

    try:
        await send_reference(nodes)
    except asyncio.CancelledError:
        raise
    except ReferenceSendError as error:
        await finish_failure(RenderFailureCategory.RENDER, "send", error)

    stats = model.stats
    orchestration_elapsed = stats.total_elapsed if stats is not None else 0.0
    log_event(
        "SUCCESS",
        "ZSSM",
        f"<g><b>request completed</b></> | "
        f"request=<c>{(perf_counter() - request_started) * 1000:.1f}ms</> "
        f"orchestration=<c>{orchestration_elapsed * 1000:.1f}ms</> "
        f"nodes=<c>{len(nodes)}</>",
    )


__all__ = ["_handle_zssm"]
