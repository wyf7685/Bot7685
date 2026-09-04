from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import Integer, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class PackageSubscription(Model):
    __tablename__ = "screen_detector_package_subscription"

    scene_persist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)


@attach_async_context(get_session)
async def add_subscription(
    session: AsyncSession,
    *,
    scene_persist_id: int,
    session_persist_id: int,
) -> bool:
    existing = await session.get(PackageSubscription, scene_persist_id)
    if existing is not None:
        existing.session_persist_id = session_persist_id
        await session.commit()
        return False
    session.add(
        PackageSubscription(
            scene_persist_id=scene_persist_id,
            session_persist_id=session_persist_id,
        )
    )
    await session.commit()
    return True


@attach_async_context(get_session)
async def remove_subscription(
    session: AsyncSession,
    scene_persist_id: int,
) -> bool:
    existing = await session.get(PackageSubscription, scene_persist_id)
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True


@attach_async_context(get_session)
async def list_subscriptions(
    session: AsyncSession,
) -> list[PackageSubscription]:
    statement = select(PackageSubscription).order_by(
        PackageSubscription.scene_persist_id
    )
    return list((await session.scalars(statement)).all())


__all__ = [
    "PackageSubscription",
    "add_subscription",
    "list_subscriptions",
    "remove_subscription",
]
