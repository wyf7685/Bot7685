import functools
from typing import TYPE_CHECKING

import anyio
import jmcomic

if TYPE_CHECKING:
    from collections.abc import (
        AsyncGenerator,
        AsyncIterable,
        Awaitable,
        Callable,
        Generator,
    )
    from types import EllipsisType


async def abatched[T](ait: AsyncIterable[T], n: int) -> AsyncGenerator[tuple[T, ...]]:
    batch: list[T] = []
    async for item in aiter(ait):
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


def flatten_exception_group[E: BaseException](
    exc_group: BaseExceptionGroup[E],
) -> Generator[E]:
    for exc in exc_group.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            yield from flatten_exception_group(exc)
        else:
            yield exc


def format_exc(exc: BaseException) -> str:
    return (str if isinstance(exc, jmcomic.JmcomicException) else repr)(exc)


def format_exc_msg(msg: str, exc: BaseException) -> str:
    return f"{msg}:\n" + (
        "\n".join(format_exc(exc) for exc in flatten_exception_group(exc))
        if isinstance(exc, BaseExceptionGroup)
        else format_exc(exc)
    )


class Task[T]:
    event: anyio.Event
    result: T | EllipsisType = ...

    def __init__(self) -> None:
        self.event = anyio.Event()

    def set_result(self, value: T) -> None:
        self.result = value
        self.event.set()

    async def wait(self) -> T:
        await self.event.wait()
        assert self.result is not ..., "Task result not set"
        return self.result
