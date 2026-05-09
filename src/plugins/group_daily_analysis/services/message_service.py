"""消息获取服务 — 基于 chatrecorder。"""

from datetime import datetime, timedelta, timezone

from nonebot.adapters import Bot
from nonebot_plugin_alconna import At, Image, Reply, Text, UniMessage
from nonebot_plugin_chatrecorder import MessageRecord, get_message_records
from nonebot_plugin_chatrecorder.message import deserialize_message
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from sqlalchemy import select

from ..domain.value_objects import (
    MessageContent,
    MessageContentType,
    UnifiedMessage,
)

UTC8 = timezone(timedelta(hours=8))


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
    user_id_map, user_name_map = await _resolve_user_info(spids)

    # 转换为统一格式
    messages: list[UnifiedMessage] = []

    for record in records:
        spid = record.session_persist_id
        sender_id = user_id_map.get(spid, str(spid))

        # 排除指定 ID
        if exclude_self_ids and sender_id in exclude_self_ids:
            continue

        sender_name = user_name_map.get(spid, sender_id)

        # 解析消息内容
        msg = _parse_record(bot, session, record, sender_id, sender_name)

        # 二次去重：过滤时间戳不严格大于水位线的消息
        if since_timestamp is not None and msg.timestamp <= since_timestamp:
            continue

        messages.append(msg)

    messages.sort(key=lambda m: m.timestamp)
    return messages


async def _resolve_user_info(
    spids: set[int],
) -> tuple[dict[int, str], dict[int, str]]:
    """通过 session_persist_id 批量查询 user_id 和 nickname。"""
    user_id_map: dict[int, str] = {}
    user_name_map: dict[int, str] = {}

    if not spids:
        return user_id_map, user_name_map

    async with get_session() as db_session:
        stmt = (
            select(SessionModel.id, UserModel)
            .where(SessionModel.id.in_(spids))
            .join(SessionModel, UserModel.id == SessionModel.user_persist_id)
        )
        rows = (await db_session.execute(stmt)).all()

    for sid, user_model in (r.tuple() for r in rows):
        user_id_map[sid] = user_model.user_id
        try:
            user = await user_model.to_user()
            user_name_map[sid] = user.nick or user.name or user.id
        except Exception:
            user_name_map[sid] = user_model.user_id

    return user_id_map, user_name_map


def _parse_record(
    bot: Bot,
    session: Session,
    record: MessageRecord,
    sender_id: str,
    sender_name: str,
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
        sender_id=sender_id,
        sender_name=sender_name,
        group_id=session.scene.id,
        text_content="".join(text_parts),
        contents=tuple(contents),
        timestamp=int(record.time.timestamp()),
        platform=str(session.adapter),
        reply_to_id=reply_to_id,
    )
