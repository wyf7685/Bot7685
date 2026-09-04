from dataclasses import dataclass

from nonebot_plugin_alconna import Target
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.orm import get_session_model, persist_session
from nonebot_plugin_uninfo.target import to_target
from sqlalchemy.exc import NoResultFound


@dataclass(frozen=True, slots=True)
class SessionReference:
    session_persist_id: int
    scene_persist_id: int


async def persist_session_reference(session: Session) -> SessionReference:
    session_model = await persist_session(session)
    return SessionReference(
        session_persist_id=session_model.id,
        scene_persist_id=session_model.scene_persist_id,
    )


async def get_session_reference(session_persist_id: int) -> SessionReference | None:
    try:
        session_model = await get_session_model(session_persist_id)
    except NoResultFound:
        return None
    return SessionReference(
        session_persist_id=session_model.id,
        scene_persist_id=session_model.scene_persist_id,
    )


async def resolve_session(session_persist_id: int) -> Session | None:
    try:
        session_model = await get_session_model(session_persist_id)
        return await session_model.to_session()
    except NoResultFound:
        return None


async def resolve_target(session_persist_id: int) -> Target | None:
    session = await resolve_session(session_persist_id)
    return to_target(session) if session is not None else None


__all__ = [
    "SessionReference",
    "get_session_reference",
    "persist_session_reference",
    "resolve_session",
    "resolve_target",
]
