import datetime
from typing import final

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


@final
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
