import contextlib
import traceback
from collections.abc import Generator, Iterable

import anyio
from nonebot import get_driver, on_type, require
from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.message import run_postprocessor, run_preprocessor

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import (
    CustomNode,
    SupportScope,
    UniMessage,
    get_message_id,
    get_target,
    message_reaction,
)

require("src.service.cache")
from src.service.cache import get_cache

driver = get_driver()
in_progess: dict[str, int] = {}
exc_cache = get_cache("matcher_exception", dict[str, tuple[str, str, str]])
exc_cache_lock = anyio.Lock()


def should_react(bot: Bot, event: Event) -> bool:
    try:
        target = get_target(event, bot)
    except NotImplementedError:
        return False
    try:
        get_message_id(event, bot)
    except Exception:
        return False

    return not target.private and target.scope == SupportScope.qq_client


async def safe_reaction(
    bot: Bot,
    event: Event,
    emoji: str,
    delete: bool = False,
) -> None:
    with contextlib.suppress(Exception):
        await message_reaction(emoji=emoji, event=event, bot=bot, delete=delete)


async def cache_exception(event: Event, matcher: Matcher, exc: Exception) -> None:
    with contextlib.suppress(Exception):
        message_id = get_message_id(event)
        source = (
            "<unknown>"
            if (_source := matcher._source) is None  # noqa: SLF001
            else f"File {str(_source.file)!r}, line {_source.lineno}"
        )
        trace = "".join(traceback.format_exception(exc))

        async with exc_cache_lock:
            cached = await exc_cache.get(message_id, {})
            cached[source] = repr(matcher), repr(exc), trace
            await exc_cache.set(message_id, cached)


@run_preprocessor
async def reaction_before_matcher(bot: Bot, event: Event) -> None:
    if should_react(bot, event):
        message_id = get_message_id(event)
        in_progess[message_id] = in_progess.get(message_id, 0) + 1
        driver.task_group.start_soon(safe_reaction, bot, event, "60")  # coffee


@run_postprocessor
async def reaction_after_matcher(
    bot: Bot,
    event: Event,
    matcher: Matcher,
    exception: Exception | None,
) -> None:
    if should_react(bot, event):
        emoji = "144" if exception is None else "41"  # 🎉/[发抖]
        driver.task_group.start_soon(safe_reaction, bot, event, emoji)
        if exception is not None:
            driver.task_group.start_soon(cache_exception, event, matcher, exception)

        message_id = get_message_id(event)
        in_progess[message_id] = in_progess.get(message_id, 1) - 1
        if in_progess[message_id] <= 0:
            del in_progess[message_id]
            await safe_reaction(bot, event, "60", delete=True)  # coffee


with contextlib.suppress(ImportError):
    from nonebot.adapters.milky.event import GroupMessageReactionEvent

    CONTENT_MAX_LENGTH = 16_000

    def split_nodes(nodes: Iterable[CustomNode]) -> Generator[CustomNode]:
        for node in nodes:
            content = str(node.content)
            if len(content) <= CONTENT_MAX_LENGTH:
                yield node
                continue
            while content:
                split_pos = content.rfind("\n", 0, CONTENT_MAX_LENGTH)
                if split_pos == -1:
                    split_pos = CONTENT_MAX_LENGTH
                yield CustomNode(
                    uid=node.uid, name=node.name, content=content[:split_pos]
                )
                content = content[split_pos:]

    def _reaction_message_id(event: GroupMessageReactionEvent) -> str:
        return f"{event.data.message_seq}@group:{event.data.group_id}"

    async def _reaction_rule(event: GroupMessageReactionEvent) -> bool:
        if event.data.face_id != "289" or not event.data.is_add:  # [睁眼]
            return False
        async with exc_cache_lock:
            return await exc_cache.exists(_reaction_message_id(event))

    reaction_matcher = on_type(
        GroupMessageReactionEvent,
        rule=_reaction_rule,
        priority=10,
    )

    @reaction_matcher.handle()
    async def handle_reaction(event: GroupMessageReactionEvent) -> None:
        async with exc_cache_lock:
            cached = await exc_cache.get(_reaction_message_id(event))
        if not cached:
            return

        user_id = event.get_user_id()
        await UniMessage.reference(
            *split_nodes(
                CustomNode(
                    uid=user_id,
                    name=f"{matcher} at {source}",
                    content=f"Exception: {exc}\n"
                    f"Matcher: {matcher}\n"
                    f"Source: {source}\n"
                    f"\n\n{trace}",
                )
                for source, (matcher, exc, trace) in cached.items()
            )
        ).send()
