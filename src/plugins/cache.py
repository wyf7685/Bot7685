import functools
from collections.abc import Awaitable, Iterable
from typing import Literal, Protocol, overload

from aiocache import BaseCache, RedisCache, SimpleMemoryCache
from aiocache.serializers import PickleSerializer
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


class Cache[KT, VT](Protocol):
    async def add(self, key: KT, value: VT, ttl: int = ...) -> None: ...
    @overload
    async def get(self, key: KT) -> VT | None: ...
    @overload
    async def get[T](self, key: KT, default: T) -> VT | T: ...
    async def multi_get(self, keys: list[KT]) -> list[VT | None]: ...
    async def set(self, key: KT, value: VT, ttl: int = ...) -> None: ...
    async def multi_set(
        self, pairs: Iterable[tuple[KT, VT]], ttl: int = ...
    ) -> None: ...
    async def delete(self, key: KT) -> None: ...
    async def exists(self, key: KT) -> bool: ...
    async def increment(self, key: KT, delta: int = 1) -> int: ...
    async def expire(self, key: KT, ttl: int) -> bool: ...
    async def clear(self) -> Literal[True]: ...


_cache: BaseCache | None = None
_cache_pickle: BaseCache | None = None


def _get_cache(*, pickle: bool) -> BaseCache:
    global _cache_pickle, _cache

    if pickle and _cache_pickle:
        return _cache_pickle
    if not pickle and _cache:
        return _cache

    serializer = PickleSerializer() if pickle else None
    if redis_config := get_plugin_config(Config).redis:
        cache = RedisCache(
            serializer,
            endpoint=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password,
        )
    else:
        cache = SimpleMemoryCache(serializer)

    if pickle:
        _cache_pickle = cache
    else:
        _cache = cache

    return cache


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


class CacheWrapper[KT, VT]:
    def __init__(self, namespace: str, *, pickle: bool) -> None:
        self.__namespace = f"bot7685:{namespace}:"
        self.__pickle = pickle

    def __getattr__(self, name: str, /) -> object:
        func = getattr(_get_cache(pickle=self.__pickle), name)
        return (
            functools.partial(func, namespace=self.__namespace)
            if name in _METHOD_WITH_NS
            else func
        )


class get_cache[KT, VT]:  # noqa: N801
    def __new__(cls, namespace: str, *, pickle: bool = False) -> Cache[KT, VT]:
        return CacheWrapper(namespace, pickle=pickle)  # pyright:ignore[reportReturnType]


class cache_with[*Ts]:  # noqa: N801
    def __new__[R](
        cls,
        namespace: str,
        key: Callable[[*Ts], object],
        *,
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


async def dispose() -> None:
    if _cache:
        await _cache.close()
    if _cache_pickle:
        await _cache_pickle.close()
