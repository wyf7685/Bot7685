import datetime as dt

import sqlalchemy as sa
from nonebot_plugin_chatrecorder.model import MessageRecord
from nonebot_plugin_chatrecorder.record import filter_statement
from nonebot_plugin_orm import get_scoped_session
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.model import User
from nonebot_plugin_uninfo.orm import BotModel, SceneModel, SessionModel, UserModel


async def query_session(session: Session, days: int = 30) -> dict[dt.date, int]:
    stop = dt.datetime.now()
    start = stop - dt.timedelta(days=days)
    whereclause = filter_statement(
        session=session,
        filter_self_id=True,
        filter_adapter=True,
        filter_scope=True,
        filter_scene=True,
        filter_user=True,
        time_start=start,
        time_stop=stop,
        types=["message"],
    )
    result = await get_scoped_session().execute(
        sa.select(
            date := sa.func.date(MessageRecord.time),
            sa.func.count(MessageRecord.id),
        )
        .where(*whereclause)
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .join(BotModel, BotModel.id == SessionModel.bot_persist_id)
        .join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
        .join(UserModel, UserModel.id == SessionModel.user_persist_id)
        .group_by(date)
        .order_by(date.asc())
    )

    data = {row[0]: row[1] for row in result}
    if data and isinstance(next(iter(data)), str):
        data = {dt.datetime.strptime(k, "%Y-%m-%d").date(): v for k, v in data.items()}  # noqa: DTZ007
    return data


async def query_scene(
    session: Session,
    days: int = 7,
    num: int = 5,
) -> dict[str, tuple[User, int]]:
    stop = dt.datetime.now()
    start = stop - dt.timedelta(days=days)
    whereclause = filter_statement(
        session=session,
        filter_self_id=True,
        filter_adapter=True,
        filter_scope=True,
        filter_scene=True,
        filter_user=False,
        time_start=start,
        time_stop=stop,
        types=["message"],
    )

    db = get_scoped_session()
    result = await db.execute(
        sa.select(UserModel.id, sa.func.count(MessageRecord.id))
        .where(*whereclause)
        .join(SessionModel, SessionModel.id == MessageRecord.session_persist_id)
        .join(BotModel, BotModel.id == SessionModel.bot_persist_id)
        .join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
        .join(UserModel, UserModel.id == SessionModel.user_persist_id)
        .group_by(UserModel.id)
        .order_by(sa.func.count(MessageRecord.id).desc())
        .limit(num),
    )
    data: dict[int, int] = {row[0]: row[1] for row in result}
    return {
        m.user_id: (await m.to_user(), data[m.id])
        for m in await db.scalars(sa.select(UserModel).where(UserModel.id.in_(data)))
    }
