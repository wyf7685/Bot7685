import traceback

import anyio
from nonebot.matcher import Matcher
from pydantic import BaseModel

from src.service.cache import get_cache


class ExceptionRecord(BaseModel):
    source: str
    """匹配器定义位置, 形如 ``File '...', line 12``"""
    matcher: str
    exception: str
    traceback: str


_cache = get_cache("matcher_exception", dict[str, ExceptionRecord])
_lock = anyio.Lock()


def _source_of(matcher: Matcher) -> str:
    source = matcher._source  # noqa: SLF001
    if source is None:
        return "<unknown>"
    return f"File {str(source.file)!r}, line {source.lineno}"


async def add(message_id: str, matcher: Matcher, exc: Exception) -> None:
    record = ExceptionRecord(
        source=_source_of(matcher),
        matcher=repr(matcher),
        exception=repr(exc),
        traceback="".join(traceback.format_exception(exc)),
    )
    async with _lock:
        cached = await _cache.get(message_id, {})
        cached[record.source] = record
        await _cache.set(message_id, cached)


async def get(message_id: str) -> list[ExceptionRecord]:
    async with _lock:
        cached = await _cache.get(message_id)
    return list(cached.values()) if cached else []


async def exists(message_id: str) -> bool:
    async with _lock:
        return await _cache.exists(message_id)
