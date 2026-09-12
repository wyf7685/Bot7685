import datetime as dt
from collections.abc import AsyncIterator

from nonebot.adapters import Bot
from nonebot_plugin_alconna import At, Image, Reply, UniMessage
from nonebot_plugin_chatrecorder import MessageRecord
from nonebot_plugin_chatrecorder.message import JsonMsg, deserialize_message
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session, SupportAdapter
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from sqlalchemy import select

from src.service.uninfo_target import persist_session_reference

from .schema import AnnualMessage

UTC8 = dt.timezone(dt.timedelta(hours=8))
_STREAM_BATCH_SIZE = 500


def _to_utc_naive(value: dt.datetime) -> dt.datetime:
    return value.astimezone(dt.UTC).replace(tzinfo=None)


def _to_utc8(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.astimezone(UTC8)


async def _load_user_map(scene_persist_id: int) -> dict[int, tuple[str, str]]:
    async with get_session() as db_session:
        statement = (
            select(SessionModel.id, UserModel)
            .where(SessionModel.scene_persist_id == scene_persist_id)
            .join(UserModel, UserModel.id == SessionModel.user_persist_id)
        )
        rows = (await db_session.execute(statement)).all()

    users: dict[int, tuple[str, str]] = {}
    for session_persist_id, user_model in rows:
        user = await user_model.to_user()
        users[session_persist_id] = (
            user.id,
            user.nick or user.name or user.id,
        )
    return users


def _convert_message(
    bot: Bot | SupportAdapter | str,
    *,
    session_persist_id: int,
    message_id: str,
    occurred_at: dt.datetime,
    serialized_message: JsonMsg,
    plain_text: str,
    users: dict[int, tuple[str, str]],
) -> AnnualMessage:
    sender_id, sender_name = users.get(
        session_persist_id,
        (str(session_persist_id), str(session_persist_id)),
    )
    text = plain_text or ""
    reply_to_id: str | None = None
    message = deserialize_message(bot, serialized_message)
    if isinstance(bot, Bot):
        unimsg = UniMessage.of(message, bot=bot)
    else:
        adapter = bot.value if isinstance(bot, SupportAdapter) else bot
        unimsg = UniMessage.of(message, adapter=adapter)
    at_user_ids = [str(segment.target) for segment in unimsg[At]]
    for segment in unimsg[Image]:
        text += f"[图片:{segment.id}]"
    for segment in unimsg[Reply]:
        reply_to_id = reply_to_id or str(segment.id)

    return AnnualMessage(
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        text=text,
        occurred_at=_to_utc8(occurred_at),
        reply_to_id=reply_to_id,
        at_user_ids=tuple(at_user_ids),
    )


async def stream_analyzer_messages(
    bot: Bot | SupportAdapter | str,
    session: Session,
    year: int | None = None,
) -> AsyncIterator[tuple[AnnualMessage, ...]]:
    selected_year = year or dt.datetime.now(UTC8).year
    time_start = dt.datetime(selected_year, 1, 1, tzinfo=UTC8)
    time_stop = time_start.replace(year=selected_year + 1)
    reference = await persist_session_reference(session)
    users = await _load_user_map(reference.scene_persist_id)

    statement = (
        select(
            MessageRecord.session_persist_id,
            MessageRecord.message_id,
            MessageRecord.time,
            MessageRecord.message,
            MessageRecord.plain_text,
        )
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .where(
            SessionModel.scene_persist_id == reference.scene_persist_id,
            MessageRecord.type == "message",
            MessageRecord.time >= _to_utc_naive(time_start),
            MessageRecord.time < _to_utc_naive(time_stop),
        )
        .order_by(MessageRecord.time, MessageRecord.id)
        .execution_options(yield_per=_STREAM_BATCH_SIZE)
    )

    async with get_session() as db_session:
        result = await db_session.stream(statement)
        batch: list[AnnualMessage] = []
        async for row in result:
            batch.append(
                _convert_message(
                    bot,
                    session_persist_id=row.session_persist_id,
                    message_id=row.message_id,
                    occurred_at=row.time,
                    serialized_message=row.message,
                    plain_text=row.plain_text,
                    users=users,
                )
            )
            if len(batch) >= _STREAM_BATCH_SIZE:
                yield tuple(batch)
                batch.clear()

        if batch:
            yield tuple(batch)
