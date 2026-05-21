import asyncio
import functools
import pickle
from datetime import timedelta
from typing import cast, overload, override

import redis.asyncio as redis
from nonebot import get_driver, logger
from pydantic import TypeAdapter

from src.highlight import Highlight

from .abstract import BaseCache, BaseSerializer, CacheStats
from .config import cache_config, get_redis_config

CACHE_PREFIX = cache_config.cache_prefix


class PickleSerializer[T](BaseSerializer[T]):
    def __init__(self, protocol: int | None = None) -> None:
        self.protocol = protocol

    @override
    def dumps(self, value: T) -> bytes:
        return pickle.dumps(value, protocol=self.protocol)

    @override
    def loads(self, value: bytes) -> T:
        return pickle.loads(value)  # noqa: S301


class BytesSerializer(BaseSerializer[bytes]):
    @override
    def dumps(self, value: bytes) -> bytes:
        return value

    @override
    def loads(self, value: bytes) -> bytes:
        return value


class StringSerializer(BaseSerializer[str]):
    @override
    def dumps(self, value: str) -> bytes:
        return value.encode("utf-8")

    @override
    def loads(self, value: bytes) -> str:
        return value.decode("utf-8")


class PydanticSerializer[T](BaseSerializer[T]):
    def __init__(self, type: type[T]) -> None:  # noqa: A002
        self._adapter = TypeAdapter(type)

    @override
    def dumps(self, value: T) -> bytes:
        return self._adapter.dump_json(value)

    @override
    def loads(self, value: bytes) -> T:
        return self._adapter.validate_json(value)


class MemoryCache(BaseCache):
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
    async def pttl(self, key: str) -> float:
        handle = self._handlers.get(key)
        if handle is None:
            return -2  # key does not exist
        remaining = handle.when() - asyncio.get_running_loop().time()
        return remaining if remaining > 0 else -1  # -1 means no expiration


class RedisCache(BaseCache):
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
    async def pttl(self, key: str) -> float:
        ttl: int = await self._redis.pttl(key)
        if ttl < 0:
            return ttl
        return ttl / 1000.0


class CacheAdapter[T]:
    def __init__(
        self,
        impl: BaseCache,
        namespace: str,
        serializer: BaseSerializer[T],
    ) -> None:
        self._impl = impl
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
        value = await self._impl.get(self._format_key(key))
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
        return await self._impl.set(
            self._format_key(key),
            self._serializer.dumps(value),
            ttl.total_seconds() if isinstance(ttl, timedelta) else float(ttl),
        )

    async def exists(self, key: str) -> bool:
        return await self._impl.exists(self._format_key(key))

    async def delete(self, key: str) -> bool:
        return await self._impl.delete(self._format_key(key))

    async def pttl(self, key: str) -> float:
        return await self._impl.pttl(self._format_key(key))

    def stats(self) -> CacheStats:
        return CacheStats(hits=self._cache_hits, misses=self._cache_misses)


def get_serializer[T](type: type[T], pickle: bool) -> BaseSerializer[T]:  # noqa: A002
    if pickle:
        return PickleSerializer()
    if type is bytes:
        return cast("BaseSerializer[T]", BytesSerializer())
    if type is str:
        return cast("BaseSerializer[T]", StringSerializer())
    return PydanticSerializer(type)


_redis_client: redis.Redis | None = None


@get_driver().on_shutdown
async def _close_redis_client() -> None:
    global _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis client")
        await _redis_client.aclose()
        _redis_client = None
    get_cache_impl.cache_clear()


@functools.cache
def get_cache_impl() -> BaseCache:
    if (redis_config := get_redis_config()) is None:
        logger.info("No Redis configuration found, using in-memory cache")
        return MemoryCache()

    global _redis_client
    if _redis_client is None:
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

    return RedisCache(_redis_client)
