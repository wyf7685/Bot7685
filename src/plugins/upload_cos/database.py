from datetime import datetime

from nonebot_plugin_orm import Model, get_session
from sqlalchemy import FLOAT, TEXT, delete, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column


class CosUploadFile(Model):
    __table_args__ = {"extend_existing": True}

    key: Mapped[str] = mapped_column(TEXT)
    expire_at: Mapped[float] = mapped_column(FLOAT)


async def update_key(key: str, expire: float):
    now = datetime.now().timestamp()
    select_ = select(CosUploadFile).where(CosUploadFile.key == key)

    async with get_session() as session:
        stmt = (
            update(CosUploadFile).where(CosUploadFile.key == key)
            if (await session.scalars(select_)).all()
            else insert(CosUploadFile).values(key=key)
        ).values(expire_at=now + expire)
        await session.execute(stmt)
        await session.commit()


async def pop_expired():
    now = datetime.now().timestamp()
    select_ = select(CosUploadFile).where(CosUploadFile.expire_at <= now).limit(1)
    async with get_session() as session:
        while data := await session.scalar(select_):
            yield data.key
            stmt = delete(CosUploadFile).where(CosUploadFile.key == data.key)
            await session.execute(stmt)
            await session.commit()
