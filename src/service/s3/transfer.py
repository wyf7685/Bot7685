import contextlib
from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Buffer
from os import PathLike
from pathlib import Path
from typing import Self, assert_never, cast

import anyio
import anyio.lowlevel
import ayafileio
import httpx
from nonebot.utils import escape_tag

from src.utils import logger_wrapper

from .client import AsyncS3Client, CompletedPart, S3HttpStatusError
from .runtime import S3Runtime

UPLOAD_CHUNK_SIZE = 5 * 1024 * 1024
_RETRY_BACKOFF_SECONDS = 0.5

type UploadSource = Buffer | str | PathLike[str] | AsyncIterable[Buffer]


class MultipartUploadTask:
    def __init__(self, client: AsyncS3Client, key: str) -> None:
        self.client = client
        self.key = key
        self.upload_id = ""
        self.parts: list[CompletedPart] = []
        self._next_part_number = 1
        self._parts_lock = anyio.Lock()
        self.log = logger_wrapper(f"s3.multipart {escape_tag(key)}")

    @classmethod
    @contextlib.asynccontextmanager
    async def create(
        cls,
        client: AsyncS3Client,
        key: str,
    ) -> AsyncGenerator[Self]:
        task = cls(client, key)
        task.upload_id = await client.create_multipart_upload(key)
        try:
            yield task
            await task.complete()
        except BaseException as primary:
            abort_error: BaseException | None = None
            with anyio.CancelScope(shield=True):
                try:
                    await task.abort()
                except BaseException as secondary:
                    abort_error = secondary
            if abort_error is not None:
                raise BaseExceptionGroup(
                    "S3 multipart upload and abort both failed",
                    [primary, abort_error],
                ) from None
            raise

    def next_part_number(self) -> int:
        value = self._next_part_number
        self._next_part_number += 1
        return value

    @staticmethod
    def _is_retryable(error: BaseException) -> bool:
        if isinstance(error, httpx.RequestError):
            return True
        return isinstance(error, S3HttpStatusError) and (
            error.status_code == 429 or error.status_code >= 500
        )

    async def put_chunk(self, part_number: int, chunk: bytes) -> None:
        last_error: BaseException | None = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                etag = await self.client.upload_part(
                    key=self.key,
                    data=chunk,
                    part_number=part_number,
                    upload_id=self.upload_id,
                )
            except (httpx.RequestError, S3HttpStatusError) as error:
                if not self._is_retryable(error):
                    raise
                last_error = error
                self.log.warning(
                    f"part {part_number} attempt {attempt + 1} failed",
                    error,
                )
                if attempt + 1 < max_attempts:
                    await anyio.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
            else:
                break
        else:
            raise RuntimeError(
                f"failed to upload part {part_number} after {max_attempts} attempts"
            ) from last_error

        part: CompletedPart = {"PartNumber": part_number, "ETag": etag}
        async with self._parts_lock:
            self.parts.append(part)

    async def complete(self) -> None:
        self.parts.sort(key=lambda part: part["PartNumber"])
        await self.client.complete_multipart_upload(
            key=self.key,
            upload_id=self.upload_id,
            parts=self.parts,
        )

    async def abort(self) -> None:
        await self.client.abort_multipart_upload(
            key=self.key,
            upload_id=self.upload_id,
        )

    async def upload_from(
        self,
        chunks: AsyncIterable[bytes],
        *,
        max_workers: int,
    ) -> None:
        async def consume(
            receive: AsyncIterable[tuple[int, bytes]],
        ) -> None:
            async for part_number, chunk in receive:
                await self.put_chunk(part_number, chunk)

        send, receive = anyio.create_memory_object_stream[tuple[int, bytes]](
            max(max_workers * 2, 1)
        )
        async with anyio.create_task_group() as task_group, send:
            for _ in range(max_workers):
                task_group.start_soon(consume, receive.clone())
            receive.close()
            async for chunk in chunks:
                await send.send((self.next_part_number(), chunk))


async def _coalesce_chunks(
    source: AsyncIterable[Buffer],
    chunk_size: int = UPLOAD_CHUNK_SIZE,
) -> AsyncIterator[bytes]:
    buffer = bytearray()
    async for chunk in source:
        view = memoryview(chunk)
        if not view:
            continue
        buffer.extend(view)
        while len(buffer) >= chunk_size:
            yield bytes(buffer[:chunk_size])
            del buffer[:chunk_size]
    if buffer:
        yield bytes(buffer)


async def _buffer_source(data: Buffer) -> AsyncIterator[memoryview[int]]:
    view = memoryview(data).toreadonly()
    for offset in range(0, len(view), UPLOAD_CHUNK_SIZE):
        yield view[offset : offset + UPLOAD_CHUNK_SIZE]
        await anyio.lowlevel.checkpoint()


async def _path_source(path: Path) -> AsyncIterator[bytes]:
    async with ayafileio.open(path, "rb") as stream:
        while chunk := await stream.read(UPLOAD_CHUNK_SIZE):
            yield chunk


@contextlib.asynccontextmanager
async def _url_source(
    runtime: S3Runtime,
    url: str,
) -> AsyncIterator[AsyncIterable[bytes]]:
    async with runtime.require_source_client().stream("GET", url) as response:
        response.raise_for_status()
        yield response.aiter_bytes(UPLOAD_CHUNK_SIZE)


async def upload_source(
    runtime: S3Runtime,
    source: UploadSource,
    *,
    key: str,
) -> None:
    match source:
        case Buffer():
            chunks = _buffer_source(source)
            await upload_stream(runtime, chunks, key=key)
        case str() if source.startswith(("http://", "https://")):
            async with _url_source(runtime, source) as chunks:
                await upload_stream(runtime, chunks, key=key)
        case str():
            raise ValueError(f"Invalid source URL: {source}")
        case PathLike():
            path = Path(cast("PathLike[str]", source))
            await upload_stream(runtime, _path_source(path), key=key)
        case AsyncIterable():
            await upload_stream(runtime, source, key=key)
        case _:
            assert_never(source)


async def upload_stream(
    runtime: S3Runtime,
    source: AsyncIterable[Buffer],
    *,
    key: str,
) -> None:
    chunks = aiter(_coalesce_chunks(source))
    first = await anext(chunks, None)
    if first is None:
        await runtime.client.put_object(key, b"")
        return
    second = await anext(chunks, None)
    if second is None:
        await runtime.client.put_object(key, first)
        return

    async with (
        MultipartUploadTask.create(runtime.client, key) as task,
        anyio.create_task_group() as task_group,
    ):
        task_group.start_soon(task.put_chunk, task.next_part_number(), first)
        task_group.start_soon(task.put_chunk, task.next_part_number(), second)
        await anyio.lowlevel.checkpoint()
        await task.upload_from(
            chunks,
            max_workers=int(runtime.config.max_concurrency),
        )


__all__ = ["UPLOAD_CHUNK_SIZE", "UploadSource", "upload_source"]
