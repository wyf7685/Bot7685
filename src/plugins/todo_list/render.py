import functools
import operator
from collections.abc import Callable, Hashable
from typing import Generic, ParamSpec, Protocol, TypeVar, cast

from nonebot_plugin_htmlrender import md_to_pic
from tarina.lru import LRU

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class AsyncCallable(Protocol, Generic[P, R]):
    async def __call__(self, *args: P.args, **kwds: P.kwargs) -> R: ...


class _AsyncLruWrapped(AsyncCallable[P, R], Generic[P, R]):
    def cache_clear(self) -> None: ...


def _async_lru_cache_wrapper(
    call: AsyncCallable[P, R],
    maxsize: int,
) -> _AsyncLruWrapped[P, R]:
    lru: LRU[Hashable, R] = LRU(maxsize)
    mark = (object(),)

    def make_key(*args: P.args, **kwargs: P.kwargs) -> Hashable:
        key = args
        if kwargs:
            key = functools.reduce(operator.iconcat, kwargs.items(), key + mark)
        elif len(key) == 1 and type(key[0]) in {int, str}:
            return key[0]
        return tuple(key)

    @functools.wraps(call)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        key = make_key(*args, **kwargs)
        if not lru.has_key(key):
            lru[key] = await call(*args, **kwargs)
        return lru[key]

    setattr(wrapper, "cache_clear", lambda: lru.clear())
    return cast(_AsyncLruWrapped[P, R], wrapper)


def _lru_cache(maxsize: int) -> Callable[[AsyncCallable[P, R]], _AsyncLruWrapped[P, R]]:

    def decorator(call: AsyncCallable[P, R]) -> _AsyncLruWrapped[P, R]:
        return _async_lru_cache_wrapper(call, maxsize)

    return decorator


@_lru_cache(1 << 4)
async def render_markdown(md: str) -> bytes:
    return await md_to_pic(md)
