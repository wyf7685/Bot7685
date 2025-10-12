import functools
from collections.abc import Awaitable
from typing import TYPE_CHECKING

from aiocache import BaseCache, RedisCache, SimpleMemoryCache
from aiocache.serializers import PickleSerializer
from common import Callable
from nonebot import get_driver, get_plugin_config
from pydantic import BaseModel

if TYPE_CHECKING:
    from .cache import Cache  # ./cache.pyi


class RedisConfig(BaseModel):
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None


class Config(BaseModel):
    redis: RedisConfig | None = None


_redis_config = get_plugin_config(Config).redis


def _get_cache(*, pickle: bool) -> BaseCache:
    serializer = PickleSerializer() if pickle else None
    return (
        RedisCache(
            serializer,
            endpoint=_redis_config.host,
            port=_redis_config.port,
            db=_redis_config.db,
            password=_redis_config.password,
        )
        if _redis_config is not None
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


class get_cache[KT, VT]:  # noqa: N801
    def __new__(cls, namespace: str, *, pickle: bool = False) -> Cache[KT, VT]:
        return CacheWrapper(namespace, pickle=pickle)  # pyright:ignore[reportReturnType]


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
