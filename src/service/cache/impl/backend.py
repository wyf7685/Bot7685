import asyncio
import functools
from typing import TYPE_CHECKING, override

from nonebot import get_driver, logger

from src.highlight import Highlight

from ..abstract import PTTL, BaseCacheBackend
from ..config import get_redis_config

if TYPE_CHECKING:
    import redis.asyncio as redis


class MemoryCacheBackend(BaseCacheBackend):
    def __init__(self) -> None:
        self._cache: dict[str, bytes] = {}
        self._handlers: dict[str, asyncio.TimerHandle] = {}

    def _delete(self, key: str) -> bool:
        if self._cache.pop(key, None) is not None:
            handle = self._handlers.pop(key, None)
            if handle:
                handle.cancel()
            return True

        return False

    @override
    async def get(self, key: str) -> bytes | None:
        return self._cache.get(key)

    @override
    async def set(self, key: str, value: bytes, ttl: float) -> bool:
        self._cache[key] = value
        if key in self._handlers:
            self._handlers[key].cancel()
        loop = asyncio.get_running_loop()
        self._handlers[key] = loop.call_later(ttl, self._delete, key)
        return True

    @override
    async def exists(self, key: str) -> bool:
        return key in self._cache

    @override
    async def delete(self, key: str) -> bool:
        return self._delete(key)

    @override
    async def pttl(self, key: str) -> PTTL:
        if key not in self._cache:
            return -2  # key does not exist
        handle = self._handlers.get(key)
        if handle is None:
            return -1  # key exists but has no expiration
        remaining = handle.when() - asyncio.get_running_loop().time()
        return max(remaining, 0.0)


class RedisCacheBackend(BaseCacheBackend):
    def __init__(self, redis: redis.Redis) -> None:
        self._redis = redis

    @override
    async def get(self, key: str) -> bytes | None:
        return await self._redis.get(key)

    @override
    async def set(self, key: str, value: bytes, ttl: float) -> bool:
        return await self._redis.set(key, value, px=int(ttl * 1000))

    @override
    async def exists(self, key: str) -> bool:
        return await self._redis.exists(key) > 0

    @override
    async def delete(self, key: str) -> bool:
        return await self._redis.delete(key) > 0

    @override
    async def pttl(self, key: str) -> PTTL:
        ttl: int = await self._redis.pttl(key)
        if ttl < 0:
            return ttl  # -2 or -1
        return ttl / 1000.0  # milliseconds to seconds


_redis_client: redis.Redis | None = None


@get_driver().on_shutdown
async def _close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis client")
        await _redis_client.aclose()
        _redis_client = None
    get_cache_backend.cache_clear()


@functools.cache
def get_cache_backend() -> BaseCacheBackend:
    if (redis_config := get_redis_config()) is None:
        logger.info("No Redis configuration found, using in-memory cache")
        return MemoryCacheBackend()

    global _redis_client
    if _redis_client is None:
        import redis.asyncio as redis

        logger.opt(colors=True).info(
            f"Creating Redis client with config: {Highlight.apply(redis_config)}"
        )
        connection_pool = redis.ConnectionPool(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password_value,
            decode_responses=False,
            client_name="Bot7685",
        )
        _redis_client = redis.Redis.from_pool(connection_pool)

    return RedisCacheBackend(_redis_client)
