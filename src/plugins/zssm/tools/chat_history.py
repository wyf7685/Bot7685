import json
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from nonebot_plugin_alconna import (
    At,
    AtAll,
    Audio,
    Button,
    Emoji,
    File,
    Hyper,
    Image,
    Keyboard,
    Other,
    Reference,
    Reply,
    Segment,
    Text,
    UniMessage,
    Video,
    Voice,
)
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.message import deserialize_message
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import SceneType
from nonebot_plugin_uninfo.orm import BotModel, SceneModel, SessionModel, UserModel
from sqlalchemy import select

from src.service.llm import BoundTool, JSONValue, ToolOutput

from ..contracts import (
    HistoryMessage,
    HistoryStatus,
    RecentMessagesArgs,
    RecentMessagesResult,
    ZssmToolContext,
    bind_recent_messages_args,
)

_BIDI_CONTROL_CLASSES = frozenset(
    {"BN", "LRE", "RLE", "LRO", "RLO", "LRI", "RLI", "FSI", "PDI", "PDF"}
)
_UTC8 = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class _HistoryRow:
    record: MessageRecord
    adapter: str
    raw_user_id: str


async def _query_recent_rows(
    context: ZssmToolContext,
    arguments: RecentMessagesArgs,
) -> tuple[tuple[_HistoryRow, ...], bool]:
    cutoff = context.invocation.started_at - timedelta(
        minutes=arguments.lookback_minutes
    )
    whereclause = filter_statement(
        session=context.session,
        filter_user=False,
        exclude_user_ids=(context.session.self_id,),
        time_start=cutoff,
        time_stop=context.invocation.started_at,
        types=("message",),
    )
    statement = (
        select(MessageRecord, BotModel.adapter, UserModel.user_id)
        .where(*whereclause)
        .where(MessageRecord.id <= context.history_high_water)
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .join(BotModel, BotModel.id == SessionModel.bot_persist_id)
        .join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
        .join(UserModel, UserModel.id == SessionModel.user_persist_id)
    )
    if arguments.search_text is not None:
        statement = statement.where(
            MessageRecord.plain_text.icontains(
                arguments.search_text,
                autoescape=True,
            )
        )
    statement = statement.order_by(
        MessageRecord.time.desc(),
        MessageRecord.id.desc(),
    ).limit(arguments.count + 1)

    async with get_session() as database:
        rows = (await database.execute(statement)).all()
    has_more = len(rows) > arguments.count
    selected = rows[: arguments.count]
    return (
        tuple(
            _HistoryRow(record=record, adapter=adapter, raw_user_id=raw_user_id)
            for record, adapter, raw_user_id in (row.tuple() for row in selected)
        ),
        has_more,
    )


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    characters: list[str] = []
    for character in normalized:
        if character.isspace():
            characters.append(" ")
            continue
        if unicodedata.category(character) in {"Cc", "Cf", "Cs"}:
            continue
        if unicodedata.bidirectional(character) in _BIDI_CONTROL_CLASSES:
            continue
        characters.append(character)
    return " ".join("".join(characters).split())


def _segment_summary(
    context: ZssmToolContext,
    segment: Segment,
) -> tuple[str, str | None]:
    if isinstance(segment, Text):
        return _normalize_text(segment.text), None
    if isinstance(segment, At):
        if segment.flag != "user":
            return f"[mention:{segment.flag}]", None
        if segment.target == context.session.self_id:
            return "@assistant", None
        try:
            alias = context.participant_resolver.observe(
                segment.target
            ).participant_alias
        except TypeError, ValueError:
            return "[mention:user]", None
        return f"@{alias}", None
    if isinstance(segment, AtAll):
        return ("[mention:here]" if segment.here else "[mention:all]"), None
    if isinstance(segment, Image):
        image = context.message_images.register(segment)
        kind = "sticker" if image.sticker else "image"
        return f"[{kind}:{image.image_id}]", image.image_id
    if isinstance(segment, Audio):
        return "[audio]", None
    if isinstance(segment, Voice):
        return "[voice]", None
    if isinstance(segment, Video):
        return "[video]", None
    if isinstance(segment, File):
        return "[file]", None
    if isinstance(segment, Emoji):
        return "[emoji]", None
    if isinstance(segment, Reply):
        return "[reply]", None
    if isinstance(segment, Reference):
        return "[reference]", None
    if isinstance(segment, Hyper):
        return "[card]", None
    if isinstance(segment, Button):
        return "[button]", None
    if isinstance(segment, Keyboard):
        return "[keyboard]", None
    if isinstance(segment, Other):
        return "[unsupported]", None
    return "[segment]", None


def _summarize_message(
    context: ZssmToolContext,
    message: UniMessage,
) -> tuple[str, tuple[str, ...]]:
    parts: list[str] = []
    image_ids: list[str] = []
    for segment in message:
        part, image_id = _segment_summary(context, segment)
        if part:
            parts.append(part)
        if image_id is not None:
            image_ids.append(image_id)
    content = _normalize_text(" ".join(parts))
    return content or "[empty]", tuple(image_ids)


def _safe_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(_UTC8).isoformat(timespec="seconds")


def _truncate_utf8(value: str, maximum: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8")
    if len(encoded) <= maximum:
        return value, False

    marker = "…" if maximum >= len("…".encode()) else "."
    marker_bytes = len(marker.encode("utf-8"))
    budget = max(0, maximum - marker_bytes)
    prefix: list[str] = []
    used = 0
    for character in value:
        size = len(character.encode("utf-8"))
        if used + size > budget:
            break
        prefix.append(character)
        used += size
    truncated = "".join(prefix).rstrip() + marker
    if len(truncated.encode("utf-8")) > maximum:
        truncated = marker if marker_bytes <= maximum else "."[:maximum]
    return truncated or ".", True


def _message_value(message: HistoryMessage) -> dict[str, JSONValue]:
    return {
        "timestamp": message.timestamp,
        "participant_alias": message.participant_alias,
        "content": message.content,
        "image_ids": list(message.image_ids),
    }


def _result_value(result: RecentMessagesResult) -> dict[str, JSONValue]:
    messages: list[JSONValue] = [_message_value(message) for message in result.messages]
    return {
        "status": result.status.value,
        "messages": messages,
        "returned": result.returned,
        "truncated": result.truncated,
    }


def _serialized_size(result: RecentMessagesResult) -> int:
    return len(
        json.dumps(
            _result_value(result),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _fit_result_messages(
    messages_descending: list[HistoryMessage],
    *,
    maximum: int,
    already_truncated: bool,
) -> RecentMessagesResult:
    retained_descending: list[HistoryMessage] = []
    truncated = already_truncated
    for message in messages_descending:
        candidate_descending = [*retained_descending, message]
        candidate = RecentMessagesResult(
            status=HistoryStatus.AVAILABLE,
            messages=tuple(reversed(candidate_descending)),
            truncated=truncated,
        )
        if _serialized_size(candidate) <= maximum:
            retained_descending.append(message)
            continue

        truncated = True
        if retained_descending:
            break

        original = message.content
        low = 1
        high = len(original.encode("utf-8"))
        fitted: HistoryMessage | None = None
        while low <= high:
            middle = (low + high) // 2
            content, _ = _truncate_utf8(original, middle)
            shortened = HistoryMessage(
                timestamp=message.timestamp,
                participant_alias=message.participant_alias,
                content=content,
                image_ids=message.image_ids,
            )
            single = RecentMessagesResult(
                status=HistoryStatus.AVAILABLE,
                messages=(shortened,),
                truncated=True,
            )
            if _serialized_size(single) <= maximum:
                fitted = shortened
                low = middle + 1
            else:
                high = middle - 1
        if fitted is not None:
            retained_descending.append(fitted)
        break

    return RecentMessagesResult(
        status=HistoryStatus.AVAILABLE,
        messages=tuple(reversed(retained_descending)),
        truncated=truncated,
    )


async def _handle_recent_messages(
    context: ZssmToolContext,
    arguments: RecentMessagesArgs,
) -> ToolOutput:
    if context.session.scene.type not in {SceneType.GROUP, SceneType.PRIVATE}:
        result = RecentMessagesResult(status=HistoryStatus.UNAVAILABLE)
        return ToolOutput(
            value=_result_value(result),
            summary="returned=0 truncated=false",
            reported_error_code="history_unsupported_scene",
        )

    try:
        rows, has_more = await _query_recent_rows(context, arguments)
    except Exception:
        result = RecentMessagesResult(status=HistoryStatus.UNAVAILABLE)
        return ToolOutput(
            value=_result_value(result),
            summary="returned=0 truncated=false",
            reported_error_code="history_query_failed",
        )

    messages_descending: list[HistoryMessage] = []
    truncated = has_more
    for row in rows:
        try:
            participant_alias = context.participant_resolver.observe(
                row.raw_user_id
            ).participant_alias
            timestamp = _safe_timestamp(row.record.time)
        except Exception:
            truncated = True
            continue

        conversion_failed = False
        image_ids: tuple[str, ...] = ()
        try:
            message = UniMessage.of(
                deserialize_message(row.adapter, row.record.message),
                adapter=row.adapter,
            )
            content, image_ids = _summarize_message(context, message)
        except Exception:
            content = _normalize_text(row.record.plain_text or "")
            content = content or "[unreadable message]"
            conversion_failed = True

        content, content_truncated = _truncate_utf8(
            content,
            context.history_config.max_message_bytes,
        )
        messages_descending.append(
            HistoryMessage(
                timestamp=timestamp,
                participant_alias=participant_alias,
                content=content,
                image_ids=image_ids,
            )
        )
        truncated = truncated or conversion_failed or content_truncated

    reported_error_code: str | None = None
    if rows and not messages_descending:
        result = RecentMessagesResult(
            status=HistoryStatus.UNAVAILABLE,
            truncated=True,
        )
        reported_error_code = "history_conversion_failed"
    else:
        result = _fit_result_messages(
            messages_descending,
            maximum=context.history_config.max_result_bytes,
            already_truncated=truncated,
        )
    return ToolOutput(
        value=_result_value(result),
        summary=(
            f"returned={result.returned} "
            f"truncated={"true" if result.truncated else "false"}"
        ),
        reported_error_code=reported_error_code,
    )


def build_recent_messages_tool(
    context: ZssmToolContext,
) -> BoundTool[ZssmToolContext, RecentMessagesArgs]:
    return BoundTool(
        name="get_recent_messages",
        description=(
            "Return recent incoming messages from the current group or private "
            "conversation, using opaque participant aliases and safe segment "
            "summaries. Image and sticker placeholders include IDs accepted by "
            "inspect_message_images."
        ),
        arguments_type=bind_recent_messages_args(context.history_config),
        context=context,
        handler=_handle_recent_messages,
    )


__all__ = ["build_recent_messages_tool"]
