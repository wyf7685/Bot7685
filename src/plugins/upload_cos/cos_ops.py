from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Self, TypedDict

import anyio
import anyio.to_thread
import httpx
from nonebot_plugin_localstore import get_plugin_cache_file
from qcloud_cos import CosConfig, CosS3Client

from .config import config

ROOT = Path("qbot/upload")
DEFAULT_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB


class _PartDict(TypedDict):
    PartNumber: int
    ETag: str


class AsyncCosS3Client:
    def __init__(self, client: CosS3Client) -> None:
        self._client = client

    async def upload_file_from_buffer(self, key: str, data: bytes) -> None:
        cache_file = get_plugin_cache_file(str(id(data)))
        await anyio.Path(cache_file).write_bytes(data)
        await self.upload_file(key, cache_file)
        await anyio.Path(cache_file).unlink()

    async def upload_file(self, key: str, path: Path) -> None:
        await anyio.to_thread.run_sync(
            self._client.upload_file, config.bucket, key, path
        )

    async def delete_object(self, key: str) -> None:
        await anyio.to_thread.run_sync(self._client.delete_object, config.bucket, key)

    async def get_presigned_url(self, key: str, method: str, expired: int) -> str:
        return await anyio.to_thread.run_sync(
            self._client.get_presigned_url, config.bucket, key, method, expired
        )

    async def put_object(self, key: str, data: bytes) -> None:
        await anyio.to_thread.run_sync(
            self._client.put_object, config.bucket, key, data
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


def get_client(retry: int = 1) -> AsyncCosS3Client:
    client = CosS3Client(
        conf=CosConfig(
            Region=config.region,
            SecretId=config.secret_id,
            SecretKey=config.secret_key,
            Token=None,
            Scheme="https",
        ),
        retry=retry,
    )
    return AsyncCosS3Client(client)


class MultipartUploadTask:
    client: AsyncCosS3Client
    key: str
    upload_id: str
    parts: list[_PartDict]

    @classmethod
    async def create(cls, key: str, client: AsyncCosS3Client | None = None) -> Self:
        self = cls()
        self.client = client or get_client()
        self.key = (ROOT / key).as_posix()
        self.upload_id = await self.client.create_multipart_upload(key)
        self.parts = []
        return self

    async def put_chunk(self, chunk: bytes) -> None:
        id_ = len(self.parts) + 1
        part: _PartDict = {"PartNumber": id_, "ETag": ""}
        self.parts.append(part)
        part["ETag"] = await self.client.upload_part(
            key=self.key, data=chunk, part_number=id_, upload_id=self.upload_id
        )

    async def complete(self) -> None:
        self.parts.sort(key=lambda x: x["PartNumber"])
        await self.client.complete_multipart_upload(
            key=self.key, upload_id=self.upload_id, parts=self.parts
        )

    async def abort(self) -> None:
        await self.client.abort_multipart_upload(key=self.key, upload_id=self.upload_id)

    async def upload_from(
        self,
        read: Callable[[], Awaitable[bytes | None]],
        max_workers: int = 4,
    ) -> None:
        async def worker() -> None:
            while (chunk := await read()) is not None:
                await self.put_chunk(chunk)

        async with anyio.create_task_group() as task_group:
            for _ in range(max_workers):
                task_group.start_soon(worker)


async def put_file(data: bytes, key: str, retry: int = 3) -> None:
    await get_client(retry).upload_file_from_buffer(
        key=(ROOT / key).as_posix(),
        data=data,
    )


async def put_file_from_local(path: Path, key: str, retry: int = 3) -> None:
    await get_client(retry).upload_file(
        key=(ROOT / key).as_posix(),
        path=path,
    )


async def delete_file(key: str, retry: int = 3) -> None:
    await get_client(retry).delete_object(
        key=(ROOT / key).as_posix(),
    )


async def presign(key: str, expired: int = 3600) -> str:
    return await get_client().get_presigned_url(
        key=(ROOT / key).as_posix(),
        method="GET",
        expired=expired,
    )


async def put_file_from_url(url: str, key: str, retry: int = 3) -> None:
    # ref: CosS3Client.upload_file_from_buffer

    async with (
        httpx.AsyncClient() as _client,
        _client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        aiterable = resp.aiter_bytes(DEFAULT_CHUNK_SIZE)

        # 读取第一个文件块，判断上传策略
        if (first_chunk := await anext(aiterable, None)) is None:
            raise ValueError("Empty file from url")

        # 小文件直接上传
        if len(first_chunk) < DEFAULT_CHUNK_SIZE:
            await get_client(retry).put_object(key=key, data=first_chunk)
            return

        # 大文件创建分块上传任务
        task = await MultipartUploadTask.create(key)
        # 上传第一个分块
        await task.put_chunk(first_chunk)
        # 上传剩余分块
        await task.upload_from(lambda: anext(aiterable, None))

    try:
        await task.complete()
    except Exception:
        await task.abort()
        raise
