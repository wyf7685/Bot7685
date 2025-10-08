import hashlib
from typing import TYPE_CHECKING, NamedTuple

from nonebot_plugin_alconna import Target
from nonebot_plugin_orm import Model, get_session
from sqlalchemy import JSON, Integer, delete, select
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from collections.abc import Iterable

type TargetDict = dict[str, object]


class PipeTuple(NamedTuple):
    listen: Target
    target: Target

    @classmethod
    def from_scalars(
        cls, pipes: Iterable[tuple[TargetDict, TargetDict]]
    ) -> list[PipeTuple]:
        return [
            cls(Target.load(listen), Target.load(target)) for listen, target in pipes
        ]


def make_key(target: Target, /) -> int:
    args = (target.id, target.channel, target.private, target.self_id)
    for k, v in target.extra.items():
        args += (k, v)
    key = "".join(map(str, args)).encode("utf-8")
    h = hashlib.md5(key).hexdigest()  # noqa: S324
    # NOTE: unsafe hash
    return int(h, 16) % (1 << 31)


class Pipe(Model):
    listen: Mapped[int] = mapped_column(Integer(), nullable=False, primary_key=True)
    """ 监听群组 """
    target: Mapped[int] = mapped_column(Integer(), nullable=False, primary_key=True)
    """ 目标群组 """
    listen_t: Mapped[TargetDict] = mapped_column(JSON(), nullable=False)
    """ 监听群组的 Target """
    target_t: Mapped[TargetDict] = mapped_column(JSON(), nullable=False)
    """ 目标群组的 Target """

    def get_listen(self) -> Target:
        return Target.load(self.listen_t)

    def get_target(self) -> Target:
        return Target.load(self.target_t)


async def get_pipes(
    *,
    listen: Target | None = None,
    target: Target | None = None,
) -> list[PipeTuple]:
    statement = select(Pipe.listen_t, Pipe.target_t)
    if listen is not None:
        statement = statement.where(Pipe.listen == make_key(listen))
    if target is not None:
        statement = statement.where(Pipe.target == make_key(target))

    async with get_session() as session:
        result = await session.execute(statement)

    return PipeTuple.from_scalars(row.tuple() for row in result.all())


async def get_linked_pipes(query: Target) -> tuple[list[PipeTuple], list[PipeTuple]]:
    key = make_key(query)

    async with get_session() as session:
        statement = select(Pipe.listen_t, Pipe.target_t).where(Pipe.listen == key)
        result = await session.execute(statement)
        listen_pipes = PipeTuple.from_scalars(row.tuple() for row in result.all())

        statement = select(Pipe.listen_t, Pipe.target_t).where(Pipe.target == key)
        result = await session.execute(statement)
        target_pipes = PipeTuple.from_scalars(row.tuple() for row in result.all())

    return listen_pipes, target_pipes


async def create_pipe(listen: Target, target: Target) -> None:
    async with get_session() as session:
        session.add(
            Pipe(
                listen=make_key(listen),
                target=make_key(target),
                listen_t=listen.dump(),
                target_t=target.dump(),
            )
        )


async def delete_pipe(pipe: PipeTuple) -> None:
    stmt = (
        delete(Pipe)
        .where(Pipe.listen == make_key(pipe.listen))
        .where(Pipe.target == make_key(pipe.target))
    )

    async with get_session() as session:
        await session.execute(stmt)


def display_pipe(listen: Target, target: Target) -> str:
    return f"<{listen.adapter}: {listen.id}> ==> <{target.adapter}: {target.id}>"
