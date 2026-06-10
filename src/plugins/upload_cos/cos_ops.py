from collections.abc import AsyncIterable, AsyncIterator, Buffer, Iterable
from pathlib import Path, PurePosixPath
from typing import Self

import anyio
import anyio.lowlevel
import ayafileio
import httpx
from nonebot import logger
from nonebot.utils import escape_tag

from src.utils import attach_async_context

from .config import config
from .cos_client import AsyncCosClient, MultipartUploadPart

ROOT = PurePosixPath("qbot/upload")
CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
DEFAULT_TTL_SECS = 3600  # 1 hour


def _create_client() -> AsyncCosClient:
    return AsyncCosClient(
        region=config.region,
        bucket=config.bucket,
        is_internal=config.is_internal,
        secret_id=config.secret_id.get_secret_value(),
        secret_key=config.secret_key.get_secret_value(),
    )


class MultipartUploadTask:
    client: AsyncCosClient
    key: str
    upload_id: str
    parts: list[MultipartUploadPart]
    _next_part_number: int
    _part_number_lock: anyio.Lock
    _parts_lock: anyio.Lock

    def __init__(self, client: AsyncCosClient, key: str) -> None:
        self.client = client
        self.key = key
        self.upload_id = ""
        self.parts = []
        self._next_part_number = 1
        self._parts_lock = anyio.Lock()

    @classmethod
    async def create(cls, client: AsyncCosClient, key: str) -> Self:
        self = cls(client, key)
        self.upload_id = await client.create_multipart_upload(self.key)
        return self

    def next_part_number(self) -> int:
        value = self._next_part_number
        self._next_part_number += 1
        return value

    async def put_chunk(self, part_number: int, chunk: bytes) -> None:
        logger.opt(colors=True).debug(
            f"Uploading part <y>{part_number}</> for key=<c>{escape_tag(self.key)}</>"
        )

        last_exc = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                etag = await self.client.upload_part(
                    key=self.key,
                    data=chunk,
                    part_number=part_number,
                    upload_id=self.upload_id,
                )
            except httpx.RequestError as exc:
                last_exc = exc
                logger.opt(colors=True).warning(
                    f"Attempt <g>{attempt + 1}</> to upload part <y>{part_number}</> "
                    f"for key=<c>{escape_tag(self.key)}</> failed: "
                    f"<r>{escape_tag(repr(exc))}</>"
                )
            else:
                break
        else:
            raise RuntimeError(
                f"Failed to upload part {part_number} for key={self.key} "
                f"after {max_attempts} attempts: {last_exc!r}"
            ) from last_exc

        part: MultipartUploadPart = {
            "PartNumber": part_number,
            "ETag": etag,
        }
        async with self._parts_lock:
            self.parts.append(part)

    async def complete(self) -> None:
        assert all(part["ETag"] for part in self.parts)
        self.parts.sort(key=lambda part: part["PartNumber"])
        await self.client.complete_multipart_upload(
            key=self.key, upload_id=self.upload_id, parts=self.parts
        )

    async def abort(self) -> None:
        await self.client.abort_multipart_upload(key=self.key, upload_id=self.upload_id)

    async def upload_from(
        self,
        aiterable: AsyncIterable[bytes],
        max_workers: int = 8,
    ) -> None:
        async def consumer(ait: AsyncIterable[tuple[int, bytes]]) -> None:
            async for part_number, chunk in ait:
                await self.put_chunk(part_number, chunk)

        send, recv = anyio.create_memory_object_stream[tuple[int, bytes]](
            max(max_workers * 2, 1)
        )
        async with anyio.create_task_group() as tg, send:
            for _ in range(max_workers):
                tg.start_soon(consumer, recv.clone())
            recv.close()
            async for chunk in aiterable:
                await send.send((self.next_part_number(), chunk))


async def _coalesce_chunks(
    aiterable: AsyncIterable[Iterable[int]],
    chunk_size: int = CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    buffer = bytearray()

    async for chunk in aiterable:
        if not chunk:
            continue

        buffer.extend(chunk)
        while len(buffer) >= chunk_size:
            yield bytes(buffer[:chunk_size])
            del buffer[:chunk_size]

    if buffer:
        yield bytes(buffer)


async def put_file_from_aiterable(
    aiterable: AsyncIterable[Iterable[int]], key: str
) -> None:
    chunk_iter = aiter(_coalesce_chunks(aiterable))
    object_key = (ROOT / key).as_posix()

    first_chunk = await anext(chunk_iter, None)
    if first_chunk is None:
        raise ValueError("Cannot upload empty file")

    second_chunk = await anext(chunk_iter, None)
    async with _create_client() as client:
        if second_chunk is None:
            await client.put_object(key=object_key, data=first_chunk)
            return

        task = await MultipartUploadTask.create(client, object_key)
        try:
            await task.put_chunk(task.next_part_number(), first_chunk)
            await task.put_chunk(task.next_part_number(), second_chunk)
            await task.upload_from(chunk_iter)
            await task.complete()
        except Exception:
            try:
                await task.abort()
            except Exception as abort_err:
                logger.opt(exception=abort_err).warning(
                    f"Failed to abort multipart upload for key={task.key}"
                )
            raise


async def put_file_from_buffer(data: Buffer, key: str) -> None:
    buf = memoryview(data).toreadonly()

    async def aiterable() -> AsyncIterable[memoryview[int]]:
        ptr = 0
        while ptr < len(buf):
            yield buf[ptr : ptr + CHUNK_SIZE]
            ptr += CHUNK_SIZE
            await anyio.lowlevel.checkpoint()

    await put_file_from_aiterable(aiterable(), key)


async def put_file_from_local(path: Path, key: str) -> None:
    async def aiterable() -> AsyncIterable[bytes]:
        async with ayafileio.open(path) as file:
            while data := await file.read(CHUNK_SIZE):
                yield data

    await put_file_from_aiterable(aiterable(), key)


@attach_async_context(_create_client)
async def delete_file(client: AsyncCosClient, key: str) -> None:
    await client.delete_object(
        key=(ROOT / key).as_posix(),
    )


@attach_async_context(_create_client)
async def presign(
    client: AsyncCosClient,
    key: str,
    ttl: int = DEFAULT_TTL_SECS,
) -> str:
    return await client.get_presigned_url(
        key=(ROOT / key).as_posix(),
        method="GET",
        expired=ttl,
    )


async def put_file_from_url(url: str, key: str) -> None:
    async with httpx.AsyncClient() as client, client.stream("GET", url) as resp:
        resp.raise_for_status()
        aiterable = resp.aiter_bytes(CHUNK_SIZE)
        await put_file_from_aiterable(aiterable, key)
