from dataclasses import dataclass
from time import time

from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import FLOAT, TEXT, delete, func, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class S3TemporaryObject(Model):
    __tablename__ = "s3_temporary_object"

    namespace: Mapped[str] = mapped_column(TEXT, primary_key=True)
    key: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


@dataclass(frozen=True, slots=True)
class ExpiredObject:
    namespace: str
    key: str


@attach_async_context(get_session)
async def record_temporary_object(
    session: AsyncSession,
    *,
    namespace: str,
    key: str,
    expires_in: float,
) -> None:
    item = await session.get(S3TemporaryObject, (namespace, key))
    expire_at = time() + expires_in
    if item is None:
        session.add(
            S3TemporaryObject(
                namespace=namespace,
                key=key,
                expire_at=expire_at,
            )
        )
    else:
        item.expire_at = expire_at
    await session.commit()


@attach_async_context(get_session)
async def has_temporary_objects(
    session: AsyncSession,
    namespace: str,
) -> bool:
    statement = (
        select(func.count())
        .select_from(S3TemporaryObject)
        .where(S3TemporaryObject.namespace == namespace)
    )
    return bool(await session.scalar(statement))


@attach_async_context(get_session)
async def list_expired_objects(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> tuple[ExpiredObject, ...]:
    statement = (
        select(S3TemporaryObject.namespace, S3TemporaryObject.key)
        .where(S3TemporaryObject.expire_at <= time())
        .order_by(S3TemporaryObject.expire_at)
        .limit(limit)
    )
    rows = (await session.execute(statement)).all()
    return tuple(ExpiredObject(namespace, key) for namespace, key in rows)


@attach_async_context(get_session)
async def forget_temporary_object(
    session: AsyncSession,
    *,
    namespace: str,
    key: str,
) -> None:
    statement = delete(S3TemporaryObject).where(
        S3TemporaryObject.namespace == namespace,
        S3TemporaryObject.key == key,
    )
    await session.execute(statement)
    await session.commit()


__all__ = [
    "ExpiredObject",
    "S3TemporaryObject",
    "forget_temporary_object",
    "has_temporary_objects",
    "list_expired_objects",
    "record_temporary_object",
]
