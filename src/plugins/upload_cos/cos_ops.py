from collections.abc import AsyncIterable
from pathlib import Path, PurePosixPath
from typing import ClassVar, Self, TypedDict, final

import anyio
import anyio.to_thread
import httpx
from qcloud_cos import CosConfig, CosS3Client

from .config import config

ROOT = PurePosixPath("qbot/upload")
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
DEFAULT_EXPIRE_SECS = 3600  # 1 hour


class _PartDict(TypedDict):
    PartNumber: int
    ETag: str


@final
class AsyncCosS3Client:
    _instance: ClassVar[Self | None] = None

    def __init__(self, client: CosS3Client) -> None:
        self._client = client

    @classmethod
    def get(cls) -> Self:
        if cls._instance is None:
            conf = CosConfig(
                Region=config.region,
                SecretId=config.secret_id.get_secret_value(),
                SecretKey=config.secret_key.get_secret_value(),
                Token=None,
                Scheme="https",
            )
            client = CosS3Client(conf, retry=3)
            cls._instance = cls(client)
        return cls._instance

    async def put_object(self, key: str, data: bytes) -> None:
        await anyio.to_thread.run_sync(
            self._client.put_object, config.bucket, data, key
        )

    async def delete_object(self, key: str) -> None:
        await anyio.to_thread.run_sync(self._client.delete_object, config.bucket, key)

    async def get_presigned_url(self, key: str, method: str, expired: int) -> str:
        return await anyio.to_thread.run_sync(
            self._client.get_presigned_url, config.bucket, key, method, expired
        )

    async def create_multipart_upload(self, key: str) -> str:
        res = await anyio.to_thread.run_sync(
            self._client.create_multipart_upload, config.bucket, key
        )
        return res["UploadId"]

    async def upload_part(
        self, key: str, data: bytes, part_number: int, upload_id: str
    ) -> str:
        res = await anyio.to_thread.run_sync(
            self._client.upload_part, config.bucket, key, data, part_number, upload_id
        )
        return res["ETag"]

    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[_PartDict]
    ) -> None:
        await anyio.to_thread.run_sync(
            self._client.complete_multipart_upload,
            config.bucket,
            key,
            upload_id,
            {"Part": parts},
        )

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        await anyio.to_thread.run_sync(
            self._client.abort_multipart_upload, config.bucket, key, upload_id
        )


class MultipartUploadTask:
    client: AsyncCosS3Client
    key: str
    upload_id: str
    parts: list[_PartDict]

    def __init__(self, key: str) -> None:
        self.client = AsyncCosS3Client.get()
        self.key = (ROOT / key).as_posix()
        self.upload_id = ""
        self.parts = []

    @classmethod
    async def create(cls, key: str) -> Self:
        self = cls(key)
        self.upload_id = await self.client.create_multipart_upload(key)
        return self

    async def put_chunk(self, chunk: bytes) -> None:
        id_ = len(self.parts) + 1
        part: _PartDict = {"PartNumber": id_, "ETag": ""}
        self.parts.append(part)
        part["ETag"] = await self.client.upload_part(
            key=self.key, data=chunk, part_number=id_, upload_id=self.upload_id
        )

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

        async def consumer(aitrable: AsyncIterable[bytes]) -> None:
            async for chunk in aitrable:
                await self.put_chunk(chunk)

        send, recv = anyio.create_memory_object_stream[bytes](0)
        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)
            for _ in range(max_workers):
                tg.start_soon(consumer, recv.clone())
            recv.close()


async def put_file_from_aiterable(aiterable: AsyncIterable[bytes], key: str) -> None:
    ait = aiter(aiterable)
    first_chunk = await anext(ait, None)
    if first_chunk is None or len(first_chunk) == 0:
        raise ValueError("Cannot upload empty file")

    if len(first_chunk) < DEFAULT_CHUNK_SIZE:
        await AsyncCosS3Client.get().put_object(
            key=(ROOT / key).as_posix(), data=first_chunk
        )
        return

    task = await MultipartUploadTask.create(key)
    try:
        await task.put_chunk(first_chunk)
        await task.upload_from(aiterable)
        await task.complete()
    except Exception:
        await task.abort()
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
    await AsyncCosS3Client.get().delete_object(
        key=(ROOT / key).as_posix(),
    )


async def presign(key: str, expired: int = DEFAULT_EXPIRE_SECS) -> str:
    return await AsyncCosS3Client.get().get_presigned_url(
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
