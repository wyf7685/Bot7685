from time import time

from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import FLOAT, TEXT, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context


class S3UploadPermission(Model):
    __tablename__ = "s3_upload_permission"

    identity: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


@attach_async_context(get_session)
async def grant_permission(
    session: AsyncSession,
    identity: str,
    expires_in: int,
) -> None:
    item = await session.get(S3UploadPermission, identity)
    expire_at = time() + expires_in
    if item is None:
        session.add(S3UploadPermission(identity=identity, expire_at=expire_at))
    else:
        item.expire_at = expire_at
    await session.commit()


@attach_async_context(get_session)
async def revoke_permission(session: AsyncSession, identity: str) -> bool:
    item = await session.get(S3UploadPermission, identity)
    if item is None:
        return False
    await session.delete(item)
    await session.commit()
    return True


@attach_async_context(get_session)
async def has_permission(session: AsyncSession, identity: str) -> bool:
    statement = select(S3UploadPermission.identity).where(
        S3UploadPermission.identity == identity,
        S3UploadPermission.expire_at > time(),
    )
    return await session.scalar(statement) is not None


@attach_async_context(get_session)
async def list_permissions(
    session: AsyncSession,
    adapter: str,
) -> tuple[tuple[str, int], ...]:
    prefix = f"{adapter}:"
    statement = (
        select(S3UploadPermission.identity, S3UploadPermission.expire_at)
        .where(
            S3UploadPermission.identity.startswith(prefix),
            S3UploadPermission.expire_at > time(),
        )
        .order_by(S3UploadPermission.expire_at)
    )
    now = time()
    rows = (await session.execute(statement)).all()
    return tuple(
        (identity.removeprefix(prefix), max(0, int(expire_at - now)))
        for identity, expire_at in rows
    )


@attach_async_context(get_session)
async def remove_expired_permissions(session: AsyncSession) -> None:
    statement = delete(S3UploadPermission).where(S3UploadPermission.expire_at <= time())
    await session.execute(statement)
    await session.commit()


__all__ = [
    "S3UploadPermission",
    "grant_permission",
    "has_permission",
    "list_permissions",
    "remove_expired_permissions",
    "revoke_permission",
]
