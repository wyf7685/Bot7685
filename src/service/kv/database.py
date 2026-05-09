from nonebot import get_driver
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import plugin_config
from .model import Base

DATABASE_URL = plugin_config.kv_cache_db_url
_engine = _sessionmaker = None


@get_driver().on_startup
async def setup_database() -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(DATABASE_URL)
    _sessionmaker = async_sessionmaker(_engine)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    if _sessionmaker is None:
        raise RuntimeError("Database not initialized")
    return _sessionmaker()
