from collections.abc import Callable, Hashable
from typing import Any, Generic, ParamSpec, Protocol, TypeVar, cast

from nonebot_plugin_htmlrender import md_to_pic

P = ParamSpec("P")
R = TypeVar("R", covariant=True)


class AsyncCallable(Protocol, Generic[P, R]):
    async def __call__(self, *args: P.args, **kwds: P.kwargs) -> R: ...


class _lru_wrapped(AsyncCallable[P, R]):
    def cache_clear(self) -> None: ...


def _make_key(
    args: tuple[Any, ...],
    kwds: dict[str, Any],
    kwd_mark: tuple[Any] = (object(),),
) -> Hashable:
    key = args
    if kwds:
        key += kwd_mark
        for item in kwds.items():
            key += item
    elif len(key) == 1 and type(key[0]) in {int, str}:
        return key[0]
    return tuple(key)


def _async_lru_cache_wrapper(
    user_function: AsyncCallable[P, R],
    maxsize: int,
) -> _lru_wrapped[P, R]:
    cache: dict[Hashable, list] = {}
    full = False
    cache_get = cache.get
    cache_len = cache.__len__
    root = []
    root[:] = [root, root, None, None]
    PREV, NEXT, KEY, RESULT = 0, 1, 2, 3

    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal root, full
        key = _make_key(args, kwargs)
        link = cache_get(key)
        if link is not None:
            link_prev, link_next, _, result = link
            link_prev[NEXT] = link_next
            link_next[PREV] = link_prev
            last = root[PREV]
            last[NEXT] = root[PREV] = link
            link[PREV] = last
            link[NEXT] = root
            return result

        result = await user_function(*args, **kwargs)
        if key in cache:
            pass
        elif full:
            oldroot = root
            oldroot[KEY] = key
            oldroot[RESULT] = result
            root = oldroot[NEXT]
            oldkey = root[KEY]
            root[KEY] = root[RESULT] = None
            del cache[oldkey]
            cache[key] = oldroot
        else:
            last = root[PREV]
            link = [last, root, key, result]
            last[NEXT] = root[PREV] = cache[key] = link
            full = cache_len() >= maxsize
        return result

    def cache_clear():
        nonlocal full
        cache.clear()
        root[:] = [root, root, None, None]
        full = False

    setattr(wrapper, "cache_clear", cache_clear)
    return cast(_lru_wrapped[P, R], wrapper)


def _lru_cache(
    maxsize: int,
) -> Callable[[AsyncCallable[P, R]], _lru_wrapped[P, R]]:

    def decorator(func) -> _lru_wrapped[P, R]:
        return _async_lru_cache_wrapper(func, maxsize)

    return decorator


@_lru_cache(1 << 4)
async def render_markdown(md: str) -> bytes:
    return await md_to_pic(md)
