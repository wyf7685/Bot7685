"""消息获取服务 — 基于 chatrecorder。"""

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from nonebot.adapters import Bot
from nonebot.exception import AdapterException
from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage
from nonebot_plugin_chatrecorder import MessageRecord, get_message_records
from nonebot_plugin_chatrecorder.message import deserialize_message
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session, get_interface
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from sqlalchemy import select

from ..domain.value_objects import (
    MessageContent,
    MessageContentType,
    UnifiedMessage,
)

UTC8 = timezone(timedelta(hours=8))


class _UserInfo(NamedTuple):
    user_id: str
    name: str
    card: str


async def fetch_group_messages(
    bot: Bot,
    session: Session,
    days: int = 1,
    exclude_self_ids: list[str] | None = None,
    since_timestamp: float | None = None,
) -> list[UnifiedMessage]:
    """从 chatrecorder 获取指定群组最近 N 天的消息并转换为统一格式。

    Args:
        session: uninfo 注入的 Session
        days: 回溯天数
        exclude_self_ids: 需要排除的发送者 ID 列表（如机器人自身）
        since_timestamp: epoch 时间戳，仅拉取此时间之后的消息（增量分析用）

    Returns:
        list[UnifiedMessage]: 按时间排序的统一消息列表
    """
    now = datetime.now(UTC8)
    time_start = now - timedelta(days=days)

    # 增量分析：确保起始时间不早于上次分析时间戳
    if since_timestamp is not None:
        since_dt = datetime.fromtimestamp(since_timestamp, tz=UTC8)
        time_start = max(time_start, since_dt)

    records = await get_message_records(
        session=session,
        filter_user=False,
        time_start=time_start,
        time_stop=now,
        types=["message"],
    )

    if not records:
        return []

    # 构建 session_persist_id -> (user_id, nickname) 映射
    spids = {r.session_persist_id for r in records}
    users = await _resolve_users(bot, session, spids)

    # 转换为统一格式
    messages: list[UnifiedMessage] = []

    for record in records:
        user = users[record.session_persist_id]

        # 排除指定 ID
        if exclude_self_ids and user.user_id in exclude_self_ids:
            continue

        # 解析消息内容
        msg = _parse_record(bot, session, record, user)

        # 二次去重：过滤时间戳不严格大于水位线的消息
        if since_timestamp is not None and msg.timestamp <= since_timestamp:
            continue

        messages.append(msg)

    messages.sort(key=lambda m: m.timestamp)
    return messages


async def _resolve_users(
    bot: Bot,
    session: Session,
    spids: set[int],
) -> dict[int, _UserInfo]:
    """通过 session_persist_id 批量查询 user_id 和 nickname。"""
    if not spids:
        return {}

    async with get_session() as db_session:
        stmt = (
            select(SessionModel.id, UserModel)
            .where(SessionModel.id.in_(spids))
            .join(SessionModel, UserModel.id == SessionModel.user_persist_id)
        )
        rows = (await db_session.execute(stmt)).all()

    interface = get_interface(bot)

    async def resolve_user(sid: int, user_model: UserModel) -> tuple[int, _UserInfo]:
        try:
            user = await user_model.to_user()
            name = user.nick or user.name or user.id
        except Exception:
            name = user_model.user_id

        member = None
        if interface is not None:
            with contextlib.suppress(NotImplementedError, AdapterException):
                member = await interface.get_member(
                    session.scene.type, session.scene.id, user_model.user_id
                )

        card = (
            member and (member.nick or member.user.nick or member.user.name)
        ) or name
        return sid, _UserInfo(user_model.user_id, name, card)

    items = await asyncio.gather(*(resolve_user(*r.tuple()) for r in rows))
    return dict(items)


def _parse_record(
    bot: Bot,
    session: Session,
    record: MessageRecord,
    user: _UserInfo,
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
        sender_id=user.user_id,
        sender_name=user.name,
        sender_card=user.card,
        group_id=session.scene.id,
        text_content="".join(text_parts),
        contents=tuple(contents),
        timestamp=int(record.time.timestamp()),
        platform=str(session.adapter),
        reply_to_id=reply_to_id,
    )
