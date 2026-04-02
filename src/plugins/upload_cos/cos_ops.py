from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path, PurePosixPath
from typing import Self

import anyio
import httpx
from nonebot import logger

from .config import config
from .cos_client import AsyncCosClient, MultipartUploadPart

ROOT = PurePosixPath("qbot/upload")
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
DEFAULT_EXPIRE_SECS = 3600  # 1 hour


def _create_client() -> AsyncCosClient:
    return AsyncCosClient(
        region=config.region,
        bucket=config.bucket,
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
        self._part_number_lock = anyio.Lock()
        self._parts_lock = anyio.Lock()

    @classmethod
    async def create(cls, client: AsyncCosClient, key: str) -> Self:
        self = cls(client, key)
        self.upload_id = await client.create_multipart_upload(self.key)
        return self

    async def put_chunk(self, chunk: bytes) -> None:
        async with self._part_number_lock:
            part_number = self._next_part_number
            self._next_part_number += 1

        etag = await self.client.upload_part(
            key=self.key,
            data=chunk,
            part_number=part_number,
            upload_id=self.upload_id,
        )

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
        async def producer() -> None:
            async with send:
                async for chunk in aiterable:
                    await send.send(chunk)

        async def consumer(aiterable_: AsyncIterable[bytes]) -> None:
            async for chunk in aiterable_:
                await self.put_chunk(chunk)

        send, recv = anyio.create_memory_object_stream[bytes](max(max_workers * 2, 1))
        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)
            for _ in range(max_workers):
                tg.start_soon(consumer, recv.clone())
            recv.close()


async def _coalesce_chunks(
    aiterable: AsyncIterable[bytes],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
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


async def put_file_from_aiterable(aiterable: AsyncIterable[bytes], key: str) -> None:
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
            async with anyio.create_task_group() as tg:
                tg.start_soon(task.put_chunk, first_chunk)
                tg.start_soon(task.put_chunk, second_chunk)
                tg.start_soon(task.upload_from, chunk_iter)
            await task.complete()
        except Exception:
            try:
                await task.abort()
            except Exception as abort_err:
                logger.opt(exception=abort_err).warning(
                    f"Failed to abort multipart upload for key={task.key}"
                )
            raise


async def put_file(data: bytes, key: str) -> None:
    async def aiterable() -> AsyncIterable[bytes]:
        ptr = 0
        while ptr < len(data):
            yield data[ptr : ptr + DEFAULT_CHUNK_SIZE]
            ptr += DEFAULT_CHUNK_SIZE

    await put_file_from_aiterable(aiterable(), key)


async def put_file_from_local(path: Path, key: str) -> None:
    async def aiterable() -> AsyncIterable[bytes]:
        while data := await file.read(DEFAULT_CHUNK_SIZE):
            yield data

    async with await anyio.Path(path).open("rb") as file:
        await put_file_from_aiterable(aiterable(), key)


async def delete_file(key: str) -> None:
    async with _create_client() as client:
        await client.delete_object(
            key=(ROOT / key).as_posix(),
        )


async def presign(key: str, expired: int = DEFAULT_EXPIRE_SECS) -> str:
    async with _create_client() as client:
        return await client.get_presigned_url(
            key=(ROOT / key).as_posix(),
            method="GET",
            expired=expired,
        )


async def put_file_from_url(url: str, key: str) -> None:
    async with (
        httpx.AsyncClient() as _client,
        _client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        aiterable = resp.aiter_bytes(DEFAULT_CHUNK_SIZE)
        await put_file_from_aiterable(aiterable, key)
