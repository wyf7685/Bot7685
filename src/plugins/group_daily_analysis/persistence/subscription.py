from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import Boolean, Integer, func, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class AnalysisSubscription(Model):
    __tablename__ = "group_daily_analysis_subscription"

    scene_persist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)
    analysis_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    incremental_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )


@attach_async_context(get_session)
async def add_subscription(
    session: AsyncSession,
    sub: AnalysisSubscription,
) -> None:
    existing = await session.get(AnalysisSubscription, sub.scene_persist_id)
    if existing is None:
        session.add(sub)
    else:
        existing.session_persist_id = sub.session_persist_id
        existing.analysis_days = sub.analysis_days
        existing.incremental_enabled = sub.incremental_enabled
    await session.commit()


@attach_async_context(get_session)
async def remove_subscription(
    session: AsyncSession,
    scene_persist_id: int,
) -> bool:
    existing = await session.get(AnalysisSubscription, scene_persist_id)
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True


@attach_async_context(get_session)
async def list_subscriptions(
    session: AsyncSession,
    *,
    scene_persist_id: int | None = None,
    incremental_only: bool = False,
) -> list[AnalysisSubscription]:
    statement = select(AnalysisSubscription).order_by(
        AnalysisSubscription.scene_persist_id
    )
    if scene_persist_id is not None:
        statement = statement.where(
            AnalysisSubscription.scene_persist_id == scene_persist_id
        )
    if incremental_only:
        statement = statement.where(AnalysisSubscription.incremental_enabled)
    return list((await session.scalars(statement)).all())


@attach_async_context(get_session)
async def count_subscriptions(session: AsyncSession) -> int:
    return int(
        await session.scalar(select(func.count(AnalysisSubscription.scene_persist_id)))
        or 0
    )
