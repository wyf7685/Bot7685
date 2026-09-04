import asyncio
from dataclasses import dataclass

from nonebot import logger
from nonebot_plugin_alconna import Target
from nonebot_plugin_orm import AsyncSession, Model, get_session
from sqlalchemy import Integer, or_, select
from sqlalchemy.orm import Mapped, mapped_column

from src.service.uninfo_target import SessionReference, resolve_target
from src.utils import attach_async_context


@dataclass(frozen=True, slots=True)
class PipeTuple:
    listen_scene_persist_id: int
    target_scene_persist_id: int
    listen: Target
    target: Target


class Pipe(Model):
    __tablename__ = "group_pipe_pipe"

    listen_scene_persist_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    target_scene_persist_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )
    listen_session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)


async def _resolve_pipe(pipe: Pipe) -> PipeTuple | None:
    listen, target = await asyncio.gather(
        resolve_target(pipe.listen_session_persist_id),
        resolve_target(pipe.target_session_persist_id),
    )
    if listen is None or target is None:
        logger.warning(
            "Pipe references missing uninfo session: "
            f"listen={pipe.listen_session_persist_id}, "
            f"target={pipe.target_session_persist_id}"
        )
        return None
    return PipeTuple(
        listen_scene_persist_id=pipe.listen_scene_persist_id,
        target_scene_persist_id=pipe.target_scene_persist_id,
        listen=listen,
        target=target,
    )


async def _resolve_pipes(pipes: list[Pipe]) -> list[PipeTuple]:
    resolved = await asyncio.gather(*map(_resolve_pipe, pipes))
    return [pipe for pipe in resolved if pipe is not None]


@attach_async_context(get_session)
async def get_pipes(
    session: AsyncSession,
    *,
    listen_scene_persist_id: int | None = None,
    target_scene_persist_id: int | None = None,
) -> list[PipeTuple]:
    statement = select(Pipe)
    if listen_scene_persist_id is not None:
        statement = statement.where(
            Pipe.listen_scene_persist_id == listen_scene_persist_id
        )
    if target_scene_persist_id is not None:
        statement = statement.where(
            Pipe.target_scene_persist_id == target_scene_persist_id
        )
    pipes = list((await session.scalars(statement)).all())
    return await _resolve_pipes(pipes)


@attach_async_context(get_session)
async def get_linked_pipes(
    session: AsyncSession,
    scene_persist_id: int,
) -> tuple[list[PipeTuple], list[PipeTuple]]:
    statement = select(Pipe).where(
        or_(
            Pipe.listen_scene_persist_id == scene_persist_id,
            Pipe.target_scene_persist_id == scene_persist_id,
        )
    )
    pipes = await _resolve_pipes(list((await session.scalars(statement)).all()))
    return (
        [pipe for pipe in pipes if pipe.listen_scene_persist_id == scene_persist_id],
        [pipe for pipe in pipes if pipe.target_scene_persist_id == scene_persist_id],
    )


@attach_async_context(get_session)
async def create_pipe(
    session: AsyncSession,
    listen: SessionReference,
    target: SessionReference,
) -> None:
    key = (listen.scene_persist_id, target.scene_persist_id)
    pipe = await session.get(Pipe, key)
    if pipe is None:
        session.add(
            Pipe(
                listen_scene_persist_id=listen.scene_persist_id,
                target_scene_persist_id=target.scene_persist_id,
                listen_session_persist_id=listen.session_persist_id,
                target_session_persist_id=target.session_persist_id,
            )
        )
    else:
        pipe.listen_session_persist_id = listen.session_persist_id
        pipe.target_session_persist_id = target.session_persist_id
    await session.commit()


@attach_async_context(get_session)
async def delete_pipe(session: AsyncSession, pipe: PipeTuple) -> None:
    row = await session.get(
        Pipe,
        (pipe.listen_scene_persist_id, pipe.target_scene_persist_id),
    )
    if row is not None:
        await session.delete(row)
        await session.commit()


def display_pipe(listen: Target, target: Target) -> str:
    return f"<{listen.adapter}: {listen.id}> ==> <{target.adapter}: {target.id}>"
