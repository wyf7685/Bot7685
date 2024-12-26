import functools
from collections.abc import Sequence
from typing import NamedTuple

from nonebot_plugin_alconna import Target
from nonebot_plugin_orm import Model, get_scoped_session
from sqlalchemy import JSON, Integer, delete, select
from sqlalchemy.orm import Mapped, mapped_column


class PipeTuple(NamedTuple):
    listen: Target
    target: Target

    @classmethod
    def from_scalars(cls, pipes: Sequence[tuple[dict, dict]]) -> list["PipeTuple"]:
        return [
            cls(Target.load(listen), Target.load(target)) for listen, target in pipes
        ]


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
    ) -> list[PipeTuple]:
        statement = select(Pipe.listen_t, Pipe.target_t)
        if listen is not None:
            statement = statement.where(Pipe.listen == make_key(listen))
        if target is not None:
            statement = statement.where(Pipe.target == make_key(target))
        result = await self.session.execute(statement)
        return PipeTuple.from_scalars([row.tuple() for row in result.all()])

    async def get_linked_pipes(
        self, query: Target
    ) -> tuple[list[PipeTuple], list[PipeTuple]]:
        key = make_key(query)

        statement = select(Pipe.listen_t, Pipe.target_t).where(Pipe.listen == key)
        result = await self.session.execute(statement)
        listen_pipes = PipeTuple.from_scalars([row.tuple() for row in result.all()])

        statement = select(Pipe.listen_t, Pipe.target_t).where(Pipe.target == key)
        result = await self.session.execute(statement)
        target_pipes = PipeTuple.from_scalars([row.tuple() for row in result.all()])

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

    async def delete_pipe(self, pipe: PipeTuple) -> None:
        statement = (
            delete(Pipe)
            .where(Pipe.listen == make_key(pipe.listen))
            .where(Pipe.target == make_key(pipe.target))
        )
        await self.session.execute(statement)
        await self.session.commit()


def display_pipe(listen: Target, target: Target) -> str:
    return f"<{listen.adapter}: {listen.id}> ==> <{target.adapter}: {target.id}>"
