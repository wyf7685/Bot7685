from datetime import timedelta
from typing import overload

from ..abstract import PTTL, BaseCacheBackend, BaseSerializer, CacheStats
from ..config import cache_config

CACHE_PREFIX = cache_config.cache_prefix


class CacheAdapter[T]:
    def __init__(
        self,
        backend: BaseCacheBackend,
        namespace: str,
        serializer: BaseSerializer[T],
    ) -> None:
        self._backend = backend
        self._namespace = namespace
        self._serializer = serializer
        self._cache_hits = 0
        self._cache_misses = 0

    def _format_key(self, key: str) -> str:
        return f"{CACHE_PREFIX}:{self._namespace}::{key}"

    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...

    async def get[D](self, key: str, default: D | None = None) -> T | D | None:
        value = await self._backend.get(self._format_key(key))
        if value is None:
            self._cache_misses += 1
            return default
        self._cache_hits += 1
        return self._serializer.loads(value)

    async def set(
        self,
        key: str,
        value: T,
        ttl: int | float | timedelta = cache_config.cache_default_ttl,
    ) -> bool:
        return await self._backend.set(
            self._format_key(key),
            self._serializer.dumps(value),
            ttl.total_seconds() if isinstance(ttl, timedelta) else float(ttl),
        )

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(self._format_key(key))

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._format_key(key))

    async def pttl(self, key: str) -> PTTL:
        return await self._backend.pttl(self._format_key(key))

    def stats(self) -> CacheStats:
        return CacheStats(hits=self._cache_hits, misses=self._cache_misses)
