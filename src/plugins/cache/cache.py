import functools
from collections.abc import Awaitable
from typing import TYPE_CHECKING, cast

from aiocache import BaseCache, RedisCache, SimpleMemoryCache
from aiocache.serializers import PickleSerializer
from common import Callable
from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel

if TYPE_CHECKING:
    from . import Cache  # type_check_only Protocol from ./__init__.pyi


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None


class Config(BaseModel):
    redis: RedisConfig | None = None


redis_config = get_plugin_config(Config).redis


def _get_cache(*, pickle: bool) -> BaseCache:
    serializer = PickleSerializer() if pickle else None
    return (
        RedisCache(
            serializer,
            endpoint=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password,
        )
        if redis_config is not None
        else SimpleMemoryCache(serializer)
    )


_METHOD_WITH_NS = {
    "add",
    "get",
    "multi_get",
    "set",
    "multi_set",
    "delete",
    "exists",
    "increment",
    "expire",
}


class CacheWrapper:
    def __init__(self, namespace: str, *, pickle: bool) -> None:
        self.__namespace = f"bot7685:{namespace}:"
        self.__cache = _get_cache(pickle=pickle)
        get_driver().on_shutdown(self.__cache.close)

    def __getattr__(self, name: str, /) -> object:
        func = getattr(self.__cache, name)
        if name in _METHOD_WITH_NS:
            func = functools.partial(func, namespace=self.__namespace)
        setattr(self, name, func)
        return func


class _Cache[KT, VT]:
    def __new__(cls, namespace: str, *, pickle: bool = False) -> Cache[KT, VT]:
        return cast("Cache[KT, VT]", CacheWrapper(namespace, pickle=pickle))


get_cache = _Cache


def cache_with[R, *Ts](
    *_: type,
    namespace: str,
    key: Callable[[*Ts], object],
    pickle: bool = False,
    ttl: int = 10 * 60,
) -> Callable[[Callable[[*Ts], Awaitable[R]]], Callable[[*Ts], Awaitable[R]]]:
    cache = get_cache[str, R](namespace, pickle=pickle)

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
