"""Message retrieval service backed by chatrecorder."""

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from nonebot.adapters import Bot
from nonebot.exception import AdapterException
from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.message import deserialize_message
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session, get_interface
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from sqlalchemy import and_, or_, select

from src.service.uninfo_target import persist_session_reference

from ..domain.value_objects import (
    MessageContent,
    MessageContentType,
    MessageCursor,
    UnifiedMember,
    UnifiedMessage,
)

UTC8 = timezone(timedelta(hours=8))


@dataclass(frozen=True, slots=True)
class IncrementalMessageBatch:
    messages: list[UnifiedMessage]
    members: set[UnifiedMember]
    last_cursor: MessageCursor | None
    has_more: bool


def _database_time(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _record_cursor(record: MessageRecord) -> MessageCursor:
    recorded_at = record.time
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=UTC)
    return MessageCursor(time=recorded_at, record_id=record.id)


async def _query_records(
    session: Session,
    *,
    days: int,
    cursor: MessageCursor | None = None,
    limit: int | None = None,
) -> tuple[list[MessageRecord], bool]:
    now = datetime.now(UTC8)
    reference = await persist_session_reference(session)
    conditions = [
        SessionModel.scene_persist_id == reference.scene_persist_id,
        MessageRecord.type == "message",
        MessageRecord.time >= _database_time(now - timedelta(days=days)),
        MessageRecord.time <= _database_time(now),
    ]
    if cursor is not None:
        cursor_time = _database_time(cursor.time)
        conditions.append(
            or_(
                MessageRecord.time > cursor_time,
                and_(
                    MessageRecord.time == cursor_time,
                    MessageRecord.id > cursor.record_id,
                ),
            )
        )

    statement = (
        select(MessageRecord)
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .where(*conditions)
        .order_by(MessageRecord.time, MessageRecord.id)
    )
    if limit is not None:
        statement = statement.limit(limit + 1)

    async with get_session() as db_session:
        records = list((await db_session.scalars(statement)).all())

    has_more = limit is not None and len(records) > limit
    if has_more:
        records = records[:limit]
    return records, has_more


async def _convert_records(
    bot: Bot,
    session: Session,
    records: list[MessageRecord],
    exclude_self_ids: list[str] | None = None,
) -> tuple[list[UnifiedMessage], set[UnifiedMember]]:
    if not records:
        return [], set()

    users = await _resolve_users(
        bot,
        session,
        {record.session_persist_id for record in records},
    )
    messages = [
        _parse_record(bot, session, record, user)
        for record in records
        if (user := users[record.session_persist_id])
        and (not exclude_self_ids or user.user_id not in exclude_self_ids)
    ]
    return messages, set(users.values())


async def fetch_group_messages(
    bot: Bot,
    session: Session,
    days: int = 1,
    exclude_self_ids: list[str] | None = None,
) -> tuple[list[UnifiedMessage], set[UnifiedMember]]:
    records, _ = await _query_records(session, days=days)
    return await _convert_records(bot, session, records, exclude_self_ids)


async def fetch_incremental_message_batch(
    bot: Bot,
    session: Session,
    *,
    days: int,
    cursor: MessageCursor | None,
    limit: int,
) -> IncrementalMessageBatch:
    records, has_more = await _query_records(
        session,
        days=days,
        cursor=cursor,
        limit=limit,
    )
    messages, members = await _convert_records(bot, session, records)
    return IncrementalMessageBatch(
        messages=messages,
        members=members,
        last_cursor=_record_cursor(records[-1]) if records else None,
        has_more=has_more,
    )


async def _resolve_users(
    bot: Bot,
    session: Session,
    spids: set[int],
) -> dict[int, UnifiedMember]:
    """通过 session_persist_id 批量查询 user_id 和 nickname。"""
    if not spids:
        return {}

    async with get_session() as db_session:
        stmt = (
            select(SessionModel.id, UserModel)
            .where(SessionModel.id.in_(spids))
            .join(SessionModel, UserModel.id == SessionModel.user_persist_id)
        )
        rows = [r.tuple() for r in (await db_session.execute(stmt)).all()]

    interface = get_interface(bot)

    async def resolve_user(
        sid: int, user_model: UserModel
    ) -> tuple[int, UnifiedMember]:
        try:
            user = await user_model.to_user()
            nickname = user.nick or user.name or user.id
        except Exception:
            nickname = user_model.user_id

        card = nickname
        avatar_url = None
        if interface is not None:
            with contextlib.suppress(NotImplementedError, AdapterException):
                member = await interface.get_member(
                    session.scene.type, session.scene.id, user_model.user_id
                )
                if member is not None:
                    card = (
                        member.nick or member.user.nick or member.user.name
                    ) or nickname
                    avatar_url = member.user.avatar

        return sid, UnifiedMember(
            user_id=user_model.user_id,
            nickname=nickname,
            card=card,
            avatar_url=avatar_url,
        )

    items = await asyncio.gather(
        *(resolve_user(sid, user_model) for sid, user_model in rows)
    )
    return dict(items)


def _parse_record(
    bot: Bot,
    session: Session,
    record: MessageRecord,
    user: UnifiedMember,
) -> UnifiedMessage:
    contents: list[MessageContent] = []
    text_parts: list[str] = []
    reply_to_id: str | None = None

    try:
        unimsg = UniMessage.of(deserialize_message(bot, record.message), bot)
    except Exception:
        unimsg = UniMessage.text(record.plain_text or "")

    for seg in unimsg:
        match seg:
            case Text(text=text):
                text_parts.append(text)
                contents.append(MessageContent(type=MessageContentType.TEXT, text=text))
            case At(target=target):
                contents.append(
                    MessageContent(type=MessageContentType.AT, at_user_id=str(target))
                )
            case Image(url=url):
                contents.append(
                    MessageContent(type=MessageContentType.IMAGE, url=url or "")
                )
            case Reply(id=reply_id):
                reply_to_id = str(reply_id)
                contents.append(MessageContent(type=MessageContentType.REPLY))

    # 用 plain_text 作为兜底
    if not text_parts and record.plain_text:
        text_parts.append(record.plain_text)

    return UnifiedMessage(
        message_id=record.message_id or str(record.id),
        sender=user,
        group_id=session.scene.id,
        text_content="".join(text_parts),
        contents=tuple(contents),
        timestamp=int(record.time.timestamp()),
        platform=str(session.adapter),
        reply_to_id=reply_to_id,
    )
