from collections.abc import AsyncGenerator, AsyncIterable


async def abatched[T](aiterable: AsyncIterable[T], n: int) -> AsyncGenerator[list[T]]:
    batch: list[T] = []
    async for item in aiterable:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch
