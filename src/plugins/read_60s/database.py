from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import CheckConstraint, Integer, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class Read60sSchedule(Model):
    __tablename__ = "read_60s_schedule"
    __table_args__ = (
        CheckConstraint("hour BETWEEN 0 AND 23", name="valid_hour"),
        CheckConstraint("minute BETWEEN 0 AND 59", name="valid_minute"),
        UniqueConstraint("scene_persist_id", "hour", "minute"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_persist_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)


@attach_async_context(get_session)
async def get_schedule(
    session: AsyncSession,
    schedule_id: int,
) -> Read60sSchedule | None:
    return await session.get(Read60sSchedule, schedule_id)


@attach_async_context(get_session)
async def find_schedule(
    session: AsyncSession,
    scene_persist_id: int,
    hour: int,
    minute: int,
) -> Read60sSchedule | None:
    statement = select(Read60sSchedule).where(
        Read60sSchedule.scene_persist_id == scene_persist_id,
        Read60sSchedule.hour == hour,
        Read60sSchedule.minute == minute,
    )
    return await session.scalar(statement)


@attach_async_context(get_session)
async def list_schedules(
    session: AsyncSession,
    *,
    scene_persist_id: int | None = None,
) -> list[Read60sSchedule]:
    statement = select(Read60sSchedule).order_by(
        Read60sSchedule.hour,
        Read60sSchedule.minute,
        Read60sSchedule.id,
    )
    if scene_persist_id is not None:
        statement = statement.where(
            Read60sSchedule.scene_persist_id == scene_persist_id
        )
    return list((await session.scalars(statement)).all())


@attach_async_context(get_session)
async def add_schedule(
    session: AsyncSession,
    schedule: Read60sSchedule,
) -> None:
    session.add(schedule)
    await session.commit()
    await session.refresh(schedule)


@attach_async_context(get_session)
async def remove_schedules(
    session: AsyncSession,
    scene_persist_id: int,
) -> list[int]:
    ids = list(
        (
            await session.scalars(
                select(Read60sSchedule.id).where(
                    Read60sSchedule.scene_persist_id == scene_persist_id
                )
            )
        ).all()
    )
    if ids:
        await session.execute(
            delete(Read60sSchedule).where(Read60sSchedule.id.in_(ids))
        )
        await session.commit()
    return ids


__all__ = [
    "Read60sSchedule",
    "add_schedule",
    "find_schedule",
    "get_schedule",
    "list_schedules",
    "remove_schedules",
]
