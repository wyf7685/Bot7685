import functools
from collections.abc import (
    AsyncGenerator,
    AsyncIterable,
    Awaitable,
    Callable,
    Generator,
)

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
    """Decorator that ensures only one instance of the decorated
    coroutine can run at a time. This decorator uses a semaphore
    to queue concurrent calls to the decorated async function,
    allowing only one execution at a time. Subsequent calls will
    wait until the running function completes.

    Args:
        func (Callable[P, Awaitable[R]]): The async function to be decorated

    Returns:
        Callable[P, Awaitable[R]]: A wrapped version of the function
        that enforces queued execution

    Example:
        ```python
        @queued
        async def my_async_func():
            # Only one instance of this function can run at a time
            await some_operation()
        ```
    """

    sem = anyio.Semaphore(1)

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        async with sem:
            return await func(*args, **kwargs)

    return wrapper


def flatten_exception_group[E: BaseException](
    exc_group: BaseExceptionGroup[E],
) -> Generator[E]:
    for exc in exc_group.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            yield from flatten_exception_group(exc)
        else:
            yield exc
