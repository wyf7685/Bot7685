import datetime
from typing import final, overload

from nonebot_plugin_orm import Model, get_scoped_session
from sqlalchemy import Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column


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


@final
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
