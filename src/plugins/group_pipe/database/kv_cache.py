import datetime

from nonebot_plugin_orm import Model, get_session
from sqlalchemy import Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column

SECONDS_PER_WEEK = 7 * 24 * 60 * 60


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


async def set_cache_value(
    adapter: str,
    key: str,
    value: str,
    expire: int = SECONDS_PER_WEEK,
) -> None:
    stmt = select(KVCache).where(KVCache.adapter == adapter).where(KVCache.key == key)

    async with get_session() as session:
        if cache := await session.scalar(stmt):
            await session.delete(cache)

        cache = KVCache(
            adapter=adapter,
            key=key,
            value=value,
            created_at=int(datetime.datetime.now().timestamp()),
            expire=expire,
        )
        session.add(cache)
        await session.commit()


async def get_cache_value(adapter: str, key: str) -> str | None:
    statement = (
        select(KVCache.value)
        .where(KVCache.adapter == adapter)
        .where(KVCache.key == key)
    )

    async with get_session() as session:
        return await session.scalar(statement)
