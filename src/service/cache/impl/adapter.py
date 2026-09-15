from collections.abc import Iterable
from datetime import timedelta
from typing import overload

import anyio.lowlevel
import nonebot

from ..abstract import PTTL, TTL, BaseCacheBackend, BaseSerializer, CacheStats
from ..config import cache_config
from ..exceptions import CacheDeserializationError, CacheSerializationError

CACHE_PREFIX = cache_config.cache_prefix


class StatsTracker:
    def __init__(self, backend: BaseCacheBackend, namespace: str) -> None:
        self._backend = backend
        self._key = f"{CACHE_PREFIX}:cache:stats::{namespace}"
        self._hits = 0
        self._misses = 0
        self._local_hits = 0
        self._local_misses = 0
        self._sync = True
        nonebot.get_driver().on_startup(self._do_sync)

    @property
    def hits(self) -> int:
        return self._hits + self._local_hits

    @property
    def misses(self) -> int:
        return self._misses + self._local_misses

    def stats(self) -> CacheStats:
        return CacheStats.of(self.hits, self.misses)

    async def _do_sync(self) -> None:
        try:
            await anyio.lowlevel.checkpoint()
            hits, misses = map(
                int,
                (await self._backend.get(self._key) or b"0|0").decode().split("|"),
            )
            self._hits = hits + self._local_hits
            self._misses = misses + self._local_misses
            self._local_hits = self._local_misses = 0
            await self._backend.set(
                self._key, f"{self._hits}|{self._misses}".encode(), ttl=None
            )
        finally:
            self._sync = False

    def _sync_stats(self) -> None:
        if self._sync:
            return
        self._sync = True
        nonebot.get_driver().task_group.start_soon(self._do_sync)

    def record_hit(self, n: int = 1) -> None:
        self._local_hits += n
        self._sync_stats()

    def record_miss(self, n: int = 1) -> None:
        self._local_misses += n
        self._sync_stats()

    def record(self, hits: int, misses: int) -> None:
        self._local_hits += hits
        self._local_misses += misses
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

    @staticmethod
    def _normalize_ttl(ttl: TTL) -> float | None:
        if ttl is None:
            return None
        if isinstance(ttl, timedelta):
            return ttl.total_seconds()
        return float(ttl)

    def _dumps(self, value: T) -> bytes:
        try:
            return self._serializer.dumps(value)
        except CacheSerializationError:
            raise
        except Exception as error:
            raise CacheSerializationError(
                f"Failed to serialize value for cache namespace {self._namespace!r}"
            ) from error

    def _loads(self, value: bytes) -> T:
        try:
            return self._serializer.loads(value)
        except CacheDeserializationError:
            raise
        except Exception as error:
            raise CacheDeserializationError(
                f"Failed to deserialize value for cache namespace {self._namespace!r}"
            ) from error

    def _loads_or_miss(self, value: bytes) -> tuple[bool, T | None]:
        try:
            return True, self._loads(value)
        except CacheDeserializationError:
            nonebot.logger.warning(
                f"Failed to deserialize value for cache namespace "
                f"{self._namespace!r}; treating it as a miss"
            )
            return False, None

    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...

    async def get[D](self, key: str, default: D | None = None) -> T | D | None:
        serialized = await self._backend.get(self._format_key(key))
        if serialized is None:
            self._tracker.record_miss()
            return default
        loaded, value = self._loads_or_miss(serialized)
        if not loaded:
            self._tracker.record_miss()
            return default
        self._tracker.record_hit()
        return value

    async def multi_get(self, keys: Iterable[str]) -> list[T | None]:
        result: list[T | None] = []
        hits = 0
        misses = 0
        for serialized in await self._backend.multi_get(map(self._format_key, keys)):
            if serialized is None:
                result.append(None)
                misses += 1
                continue
            loaded, value = self._loads_or_miss(serialized)
            result.append(value)
            if loaded:
                hits += 1
            else:
                misses += 1
        self._tracker.record(hits, misses)
        return result

    async def set(
        self,
        key: str,
        value: T,
        ttl: TTL = cache_config.cache_default_ttl,
    ) -> bool:
        return await self._backend.set(
            self._format_key(key),
            self._dumps(value),
            self._normalize_ttl(ttl),
        )

    async def multi_set(
        self,
        mapping: dict[str, T],
        ttl: TTL = cache_config.cache_default_ttl,
    ) -> int:
        serialized = {
            self._format_key(key): self._dumps(value) for key, value in mapping.items()
        }
        return await self._backend.multi_set(serialized, self._normalize_ttl(ttl))

    async def exists(self, key: str) -> bool:
        return await self._backend.exists(self._format_key(key))

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(self._format_key(key))

    async def pttl(self, key: str) -> PTTL:
        return await self._backend.pttl(self._format_key(key))

    def stats(self) -> CacheStats:
        return self._tracker.stats()
