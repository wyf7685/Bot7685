import datetime
import functools
from collections.abc import Sequence
from typing import overload

from nonebot_plugin_alconna import Target
from nonebot_plugin_orm import Model, get_scoped_session
from sqlalchemy import JSON, Integer, String, select
from sqlalchemy.orm import Mapped, mapped_column


@functools.cache
def make_key(target: Target) -> int:
    args = (target.id, target.channel, target.private, target.self_id)
    if target.extra.get("scope"):
        args += (target.extra["scope"],)
    if target.extra.get("adapter"):
        args += (str(target.extra["adapter"]),)
    key = "".join(map(str, args)).encode("utf-8")
    result = 0
    for i in key:
        result = (result << 5) - result + i
        result &= 0xFFFFFFFFFFFF
    return result % (1 << 31)


class Pipe(Model):
    listen: Mapped[int] = mapped_column(Integer(), nullable=False, primary_key=True)
    """ 监听群组 """
    target: Mapped[int] = mapped_column(Integer(), nullable=False, primary_key=True)
    """ 目标群组 """
    listen_t: Mapped[dict] = mapped_column(JSON(), nullable=False)
    """ 监听群组的 Target """
    target_t: Mapped[dict] = mapped_column(JSON(), nullable=False)
    """ 目标群组的 Target """

    def get_listen(self) -> Target:
        return Target.load(self.listen_t)

    def get_target(self) -> Target:
        return Target.load(self.target_t)


class PipeDAO:
    def __init__(self) -> None:
        self.session = get_scoped_session()

    async def get_pipes(
        self,
        *,
        listen: Target | None = None,
        target: Target | None = None,
    ) -> Sequence[Pipe]:
        statement = select(Pipe)
        if listen is not None:
            statement = statement.where(Pipe.listen == make_key(listen))
        if target is not None:
            statement = statement.where(Pipe.target == make_key(target))
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_linked_pipes(
        self, query: Target
    ) -> tuple[Sequence[Pipe], Sequence[Pipe]]:
        statement = select(Pipe).where(Pipe.listen == make_key(query))
        result = await self.session.execute(statement)
        listen_pipes = result.scalars().all()

        statement = select(Pipe).where(Pipe.target == make_key(query))
        result = await self.session.execute(statement)
        target_pipes = result.scalars().all()

        return listen_pipes, target_pipes

    async def create_pipe(self, listen: Target, target: Target) -> None:
        self.session.add(
            Pipe(
                listen=make_key(listen),
                target=make_key(target),
                listen_t=listen.dump(),
                target_t=target.dump(),
            )
        )
        await self.session.commit()

    async def delete_pipe(self, pipe: Pipe) -> None:
        await self.session.delete(pipe)
        await self.session.commit()


def display_pipe(listen: Target, target: Target) -> str:
    return f"<{listen.adapter}: {listen.id}> ==> <{target.adapter}: {target.id}>"


class MsgIdCache(Model):
    src_adapter: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 源消息适配器 """
    src_id: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 源消息 ID """
    dst_adapter: Mapped[str] = mapped_column(String(), nullable=False, primary_key=True)
    """ 目标消息适配器 """
    dst_id: Mapped[str] = mapped_column(String(), nullable=False)
    """ 目标消息 ID """
    created_at: Mapped[int] = mapped_column(Integer(), nullable=False)
    """ 创建时间 """


class MsgIdCacheDAO:
    expire_secs: int = 7 * 24 * 60 * 60  # 7 days

    def __init__(self) -> None:
        self.session = get_scoped_session()
        self.now = int(datetime.datetime.now().timestamp())

    async def clean_expired(self) -> None:
        statement = select(MsgIdCache).where(
            MsgIdCache.created_at < self.now - self.expire_secs
        )
        result = await self.session.execute(statement)
        for cache in result.scalars().all():
            await self.session.delete(cache)
        await self.session.commit()

    async def set_dst_id(
        self,
        src_adapter: str,
        src_id: str,
        dst_adapter: str,
        dst_id: str,
    ) -> None:
        await self.clean_expired()

        self.session.add(
            MsgIdCache(
                src_adapter=src_adapter,
                src_id=src_id,
                dst_adapter=dst_adapter,
                dst_id=dst_id,
                created_at=self.now,
            )
        )
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
        await self.clean_expired()

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
