import datetime
from typing import overload

from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_orm import Model, get_scoped_session, get_session
from sqlalchemy import Integer, String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

SECONDS_PER_WEEK = 7 * 24 * 60 * 60


class MsgIdCache(Model):
    src_adapter: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 源消息适配器 """
    src_id: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 源消息 ID """
    dst_adapter: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 目标消息适配器 """
    dst_id: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 目标消息 ID """
    created_at: Mapped[int] = mapped_column(Integer(), nullable=False)
    """ 创建时间 """


class MsgIdCacheDAO:
    def __init__(self) -> None:
        self.session = get_scoped_session()

    async def set_dst_id(
        self,
        src_adapter: str,
        src_id: str,
        dst_adapter: str,
        dst_id: str,
    ) -> None:
        cache = MsgIdCache(
            src_adapter=src_adapter,
            src_id=src_id,
            dst_adapter=dst_adapter,
            dst_id=dst_id,
            created_at=int(datetime.datetime.now().timestamp()),
        )
        self.session.add(cache)
        await self.session.commit()

    @overload
    async def get_reply_id(
        self,
        *,
        src_adapter: str,
        dst_adapter: str,
        src_id: str,
    ) -> str | None: ...
    @overload
    async def get_reply_id(
        self,
        *,
        src_adapter: str,
        dst_adapter: str,
        dst_id: str,
    ) -> str | None: ...

    async def get_reply_id(
        self,
        src_adapter: str,
        dst_adapter: str,
        src_id: str | None = None,
        dst_id: str | None = None,
    ) -> str | None:
        statement = (
            select(MsgIdCache.dst_id if src_id else MsgIdCache.src_id)
            .where(MsgIdCache.src_adapter == src_adapter)
            .where(MsgIdCache.dst_adapter == dst_adapter)
            .where(
                (MsgIdCache.src_id == src_id)
                if src_id
                else (MsgIdCache.dst_id == dst_id)
            )
        )
        return await self.session.scalar(statement)


class KVCache(Model):
    adapter: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 适配器 """
    key: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 缓存键 """
    value: Mapped[str] = mapped_column(String(), nullable=False)
    """ 缓存值 """
    created_at: Mapped[int] = mapped_column(Integer(), nullable=False)
    """ 创建时间 """
    expire: Mapped[int] = mapped_column(
        Integer(), default=SECONDS_PER_WEEK, nullable=False
    )
    """
    过期时间

    -1 为永不过期
    """


class KVCacheDAO:
    def __init__(self) -> None:
        self.session = get_session()

    async def set_value(
        self,
        adapter: str,
        key: str,
        value: str,
        expire: int = SECONDS_PER_WEEK,
    ) -> None:
        stmt = (
            select(KVCache).where(KVCache.adapter == adapter).where(KVCache.key == key)
        )
        if cache := await self.session.scalar(stmt):
            await self.session.delete(cache)

        cache = KVCache(
            adapter=adapter,
            key=key,
            value=value,
            created_at=int(datetime.datetime.now().timestamp()),
            expire=expire,
        )
        self.session.add(cache)
        await self.session.commit()
        await self.session.close()

    async def get_value(self, adapter: str, key: str) -> str | None:
        statement = (
            select(KVCache.value)
            .where(KVCache.adapter == adapter)
            .where(KVCache.key == key)
        )
        value = await self.session.scalar(statement)
        await self.session.close()
        return value


@scheduler.scheduled_job("interval", minutes=30)
async def auto_clean_cache() -> None:
    now = int(datetime.datetime.now().timestamp())

    async with get_session() as session:
        stmt = delete(MsgIdCache).where(MsgIdCache.created_at < now - SECONDS_PER_WEEK)
        await session.execute(stmt)
        stmt = (
            delete(KVCache)
            .where(KVCache.expire != -1)
            .where(KVCache.created_at < now - KVCache.expire)
        )
        await session.execute(stmt)
        await session.commit()
