from collections.abc import Awaitable, Callable, Iterable
from typing import Literal, Protocol, overload

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

class get_cache[KT, VT]:  # noqa: N801
    def __new__(cls, namespace: str, *, pickle: bool = False) -> Cache[KT, VT]: ...

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
