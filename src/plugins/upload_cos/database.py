from datetime import datetime
from typing import AsyncGenerator

from nonebot_plugin_orm import Model, get_session
from sqlalchemy import FLOAT, TEXT, delete, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column


class CosUploadFile(Model):
    __table_args__ = {"extend_existing": True}

    key: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


async def update_key(key: str, expired: float) -> None:
    now = datetime.now().timestamp()
    select_ = select(CosUploadFile).where(CosUploadFile.key == key)

    async with get_session() as session:
        stmt = (
            update(CosUploadFile).where(CosUploadFile.key == key)
            if (await session.scalars(select_)).all()
            else insert(CosUploadFile).values(key=key)
        ).values(expire_at=now + expired)
        await session.execute(stmt)
        await session.commit()


async def pop_expired_keys() -> AsyncGenerator[str, None]:
    now = datetime.now().timestamp()
    select_ = select(CosUploadFile).where(CosUploadFile.expire_at <= now).limit(1)
    async with get_session() as session:
        while data := await session.scalar(select_):
            yield data.key
            stmt = delete(CosUploadFile).where(CosUploadFile.key == data.key)
            await session.execute(stmt)
            await session.commit()


class CosUploadPermission(Model):
    __table_args__ = {"extend_existing": True}

    user_id: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


async def update_permission(user_id: str, expired: float) -> None:
    now = datetime.now().timestamp()
    select_ = select(CosUploadPermission).where(CosUploadPermission.user_id == user_id)

    async with get_session() as session:
        stmt = (
            update(CosUploadPermission).where(CosUploadPermission.user_id == user_id)
            if (await session.scalars(select_)).all()
            else insert(CosUploadPermission).values(user_id=user_id)
        ).values(expire_at=now + expired)
        await session.execute(stmt)
        await session.commit()


async def remove_expired_perm() -> None:
    now = datetime.now().timestamp()
    stmt = delete(CosUploadPermission).where(CosUploadFile.expire_at <= now)
    async with get_session() as session:
        await session.execute(stmt)
        await session.commit()


async def user_has_perm(user_id: str) -> bool:
    await remove_expired_perm()
    stmt = select(CosUploadPermission).where(CosUploadPermission.user_id == user_id)
    async with get_session() as session:
        return await session.scalar(stmt) is not None
