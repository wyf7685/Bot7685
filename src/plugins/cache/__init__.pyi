from collections.abc import Awaitable, Callable, Iterable
from datetime import timedelta
from typing import Final, Literal, Protocol, overload, type_check_only

class _RedisConfig(Protocol):
    host: Final[str]
    port: Final[int]
    db: Final[int]
    password: Final[str | None]

redis_config: _RedisConfig | None

@type_check_only
class Cache[T](Protocol):
    async def add(self, key: str, value: T, ttl: float | timedelta = ...) -> None: ...
    @overload
    async def get(self, key: str) -> T | None: ...
    @overload
    async def get[D](self, key: str, default: D) -> T | D: ...
    async def multi_get(self, keys: list[str]) -> list[T | None]: ...
    async def set(self, key: str, value: T, ttl: float | timedelta = ...) -> None: ...
    async def multi_set(
        self, pairs: Iterable[tuple[str, T]], ttl: float | timedelta = ...
    ) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
    async def increment(self, key: str, delta: int = 1) -> int: ...
    async def expire(self, key: str, ttl: float | timedelta) -> bool: ...
    async def clear(self) -> Literal[True]: ...

class get_cache[T]:  # noqa: N801
    def __new__(cls, namespace: str, *, pickle: bool = False) -> Cache[T]: ...

@overload
def cache_with[R](
    *,
    namespace: str,
    key: Callable[[], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[[Callable[[], Awaitable[R]]], Callable[[], Awaitable[R]]]: ...
@overload
def cache_with[R, T1](
    arg1: type[T1],
    /,
    *,
    namespace: str,
    key: Callable[[T1], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[[Callable[[T1], Awaitable[R]]], Callable[[T1], Awaitable[R]]]: ...
@overload
def cache_with[R, T1, T2](
    arg1: type[T1],
    arg2: type[T2],
    /,
    *,
    namespace: str,
    key: Callable[[T1, T2], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[[Callable[[T1, T2], Awaitable[R]]], Callable[[T1, T2], Awaitable[R]]]: ...
@overload
def cache_with[R, T1, T2, T3](
    arg1: type[T1],
    arg2: type[T2],
    arg3: type[T3],
    /,
    *,
    namespace: str,
    key: Callable[[T1, T2, T3], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[
    [Callable[[T1, T2, T3], Awaitable[R]]],
    Callable[[T1, T2, T3], Awaitable[R]],
]: ...
@overload
def cache_with[R, T1, T2, T3, T4](
    arg1: type[T1],
    arg2: type[T2],
    arg3: type[T3],
    arg4: type[T4],
    /,
    *,
    namespace: str,
    key: Callable[[T1, T2, T3, T4], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[
    [Callable[[T1, T2, T3, T4], Awaitable[R]]],
    Callable[[T1, T2, T3, T4], Awaitable[R]],
]: ...
@overload
def cache_with[R, T1, T2, T3, T4, T5](
    arg1: type[T1],
    arg2: type[T2],
    arg3: type[T3],
    arg4: type[T4],
    arg5: type[T5],
    /,
    *,
    namespace: str,
    key: Callable[[T1, T2, T3, T4, T5], object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[
    [Callable[[T1, T2, T3, T4, T5], Awaitable[R]]],
    Callable[[T1, T2, T3, T4, T5], Awaitable[R]],
]: ...
@overload
def cache_with[R](
    *_: type,
    namespace: str,
    key: Callable[..., object],
    pickle: bool = False,
    ttl: int = ...,
) -> Callable[[Callable[..., Awaitable[R]]], Callable[..., Awaitable[R]]]: ...
