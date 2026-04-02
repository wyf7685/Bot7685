from collections.abc import AsyncGenerator
from datetime import datetime

import nonebot
from nonebot.utils import escape_tag
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import Model, get_session
from sqlalchemy import FLOAT, TEXT, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from .cos_ops import delete_file


class CosUploadFile(Model):
    key: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


async def update_key(key: str, expired: float) -> None:
    expire_at = datetime.now().timestamp() + expired
    async with get_session() as session:
        if item := await session.scalar(
            select(CosUploadFile).where(CosUploadFile.key == key)
        ):
            item.expire_at = expire_at
        else:
            item = CosUploadFile(key=key, expire_at=expire_at)
            session.add(item)
        await session.commit()


async def pop_expired_keys() -> AsyncGenerator[str]:
    now = datetime.now().timestamp()
    select_ = select(CosUploadFile).where(CosUploadFile.expire_at <= now).limit(1)
    async with get_session() as session:
        while data := await session.scalar(select_):
            yield data.key
            await session.delete(data)
        await session.commit()


class CosUploadPermission(Model):
    user_id: Mapped[str] = mapped_column(TEXT, primary_key=True)
    expire_at: Mapped[float] = mapped_column(FLOAT)


async def update_permission(user_id: str, expired: float) -> None:
    expire_at = datetime.now().timestamp() + expired
    select_ = select(CosUploadPermission).where(CosUploadPermission.user_id == user_id)

    async with get_session() as session:
        if item := await session.scalar(select_):
            item.expire_at = expire_at
        else:
            item = CosUploadPermission(user_id=user_id, expire_at=expire_at)
            session.add(item)
        await session.commit()


async def remove_expired_perm() -> None:
    stmt = delete(CosUploadPermission).where(
        CosUploadPermission.expire_at <= datetime.now().timestamp()
    )
    async with get_session() as session:
        await session.execute(stmt)
        await session.commit()


async def user_has_perm(user_id: str) -> bool:
    stmt = (
        select(CosUploadPermission)
        .where(CosUploadPermission.user_id == user_id)
        .where(CosUploadPermission.expire_at > datetime.now().timestamp())
    )
    async with get_session() as session:
        return await session.scalar(stmt) is not None


@scheduler.scheduled_job("cron", minute="*/10")
async def _() -> None:
    logger = nonebot.logger.opt(colors=True)
    await remove_expired_perm()
    async for key in pop_expired_keys():
        await delete_file(key)
        logger.info(f"删除超时文件: <c>{escape_tag(key)}</c>")
