import asyncio
import functools
from collections.abc import Iterable
from datetime import timedelta
from typing import overload

from ..abstract import PTTL, BaseCacheBackend, BaseSerializer, CacheStats
from ..config import cache_config

CACHE_PREFIX = cache_config.cache_prefix


class StatsTracker:
    def __init__(self, backend: BaseCacheBackend, namespace: str) -> None:
        self._backend = backend
        self._namespace = namespace
        self._hits = 0
        self._misses = 0
        self._local_hits = 0
        self._local_misses = 0
        self._sync_task: asyncio.Task[None] | None = None

    @property
    def hits(self) -> int:
        return self._hits + self._local_hits

    @property
    def misses(self) -> int:
        return self._misses + self._local_misses

    def stats(self) -> CacheStats:
        return CacheStats(hits=self.hits, misses=self.misses)

    @functools.cached_property
    def _key_hits(self) -> str:
        return f"{CACHE_PREFIX}:cache:stats:{self._namespace}::hits"

    @functools.cached_property
    def _key_misses(self) -> str:
        return f"{CACHE_PREFIX}:cache:stats:{self._namespace}::misses"

    def _sync_stats(self) -> None:
        if self._sync_task is not None and not self._sync_task.done():
            return  # Sync already in progress

        async def sync() -> None:
            await asyncio.sleep(0)
            hits, misses = (
                int(x.decode()) if x is not None else 0
                for x in await self._backend.multi_get(
                    [self._key_hits, self._key_misses]
                )
            )
            self._hits = hits + self._local_hits
            self._misses = misses + self._local_misses
            self._local_hits = self._local_misses = 0
            await self._backend.multi_set(
                {
                    self._key_hits: str(self._hits).encode(),
                    self._key_misses: str(self._misses).encode(),
                },
                None,
            )

        self._sync_task = asyncio.get_running_loop().create_task(sync())

        @self._sync_task.add_done_callback
        def _(_: object) -> None:
            self._sync_task = None

    def record_hit(self, n: int = 1) -> None:
        self._local_hits += n
        self._sync_stats()

    def record_miss(self, n: int = 1) -> None:
        self._local_misses += n
        self._sync_stats()


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
        self._tracker = StatsTracker(backend, namespace)

    def _format_key(self, key: str) -> str:
        return f"{CACHE_PREFIX}:{self._namespace}::{key}"

    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...

    async def get[D](self, key: str, default: D | None = None) -> T | D | None:
        value = await self._backend.get(self._format_key(key))
        if value is None:
            self._tracker.record_miss()
            return default
        self._tracker.record_hit()
        return self._serializer.loads(value)

    async def multi_get(self, keys: Iterable[str]) -> list[bytes | None]:
        result = await self._backend.multi_get(map(self._format_key, keys))
        misses = sum(1 for x in result if x is None)
        hits = len(result) - misses
        self._tracker.record_hit(hits)
        self._tracker.record_miss(misses)
        return result

    async def set(
        self,
        key: str,
        value: T,
        ttl: int | float | timedelta | None = cache_config.cache_default_ttl,
    ) -> bool:
        return await self._backend.set(
            self._format_key(key),
            self._serializer.dumps(value),
            None
            if ttl is None
            else ttl.total_seconds()
            if isinstance(ttl, timedelta)
            else float(ttl),
        )

    async def multi_set(self, mapping: dict[str, bytes], ttl: float | None) -> int:
        return await self._backend.multi_set(
            {self._format_key(key): value for key, value in mapping.items()},
            ttl,
        )

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(self._format_key(key))

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._format_key(key))

    async def pttl(self, key: str) -> PTTL:
        return await self._backend.pttl(self._format_key(key))

    def stats(self) -> CacheStats:
        return self._tracker.stats()
