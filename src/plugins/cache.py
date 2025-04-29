import functools
from collections.abc import Awaitable

from aiocache import BaseCache, RedisCache, SimpleMemoryCache
from aiocache.serializers import MsgPackSerializer, PickleSerializer
from common import Callable
from nonebot import get_plugin_config
from pydantic import BaseModel


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None


class Config(BaseModel):
    redis: RedisConfig | None = None


def get_cache(namespace: str, *, pickle: bool = False) -> BaseCache:
    namespace = f"bot7685:{namespace}:"
    serializer = PickleSerializer() if pickle else MsgPackSerializer()
    if redis_config := get_plugin_config(Config).redis:
        return RedisCache(
            serializer,
            endpoint=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password,
            namespace=namespace,
        )

    return SimpleMemoryCache(serializer, namespace=namespace)


class _CacheWith[*Ts]:
    def __new__[R](
        cls, cache: BaseCache, key: Callable[[*Ts], object], /, *, ttl: int = 10 * 60
    ) -> Callable[[Callable[[*Ts], Awaitable[R]]], Callable[[*Ts], Awaitable[R]]]:
        def decorator(
            call: Callable[[*Ts], Awaitable[R]],
        ) -> Callable[[*Ts], Awaitable[R]]:
            @functools.wraps(call)
            async def wrapper(*args: *Ts) -> R:
                cache_key = str(key(*args))
                if cached := await cache.get(cache_key):
                    return cached
                result = await call(*args)
                await cache.set(cache_key, result, ttl=ttl)
                return result

            return wrapper

        return decorator


cache_with = _CacheWith
