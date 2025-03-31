import functools
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable

import anyio


async def abatched[T](
    aiterable: AsyncIterable[T], n: int
) -> AsyncGenerator[tuple[T, ...]]:
    batch: list[T] = []
    async for item in aiterable:
        batch.append(item)
        if len(batch) == n:
            yield tuple(batch)
            batch = []
    if batch:
        yield tuple(batch)


def queued[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    sem = anyio.Semaphore(1)

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with sem:
            return await func(*args, **kwargs)

    return wrapper
