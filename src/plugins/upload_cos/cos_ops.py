from pathlib import Path

import anyio
import anyio.lowlevel
import anyio.to_thread
import httpx
from qcloud_cos import CosConfig, CosS3Client

from .config import config

ROOT = Path("qbot/upload")


def new_client(retry: int = 1) -> CosS3Client:
    return CosS3Client(
        conf=CosConfig(
            Region=config.region,
            SecretId=config.secret_id,
            SecretKey=config.secret_key,
            Token=None,
            Scheme="https",
        ),
        retry=retry,
    )


async def put_file(data: bytes, key: str, retry: int = 3) -> None:
    await anyio.to_thread.run_sync(
        new_client(retry).upload_file_from_buffer,
        config.bucket,
        (ROOT / key).as_posix(),
        data,
    )


async def delete_file(key: str, retry: int = 3) -> None:
    await anyio.to_thread.run_sync(
        new_client(retry).delete_object,
        config.bucket,
        (ROOT / key).as_posix(),
    )


async def presign(key: str, expired: int = 3600) -> str:
    return await anyio.to_thread.run_sync(
        new_client().get_presigned_url,
        config.bucket,
        (ROOT / key).as_posix(),
        "GET",
        expired,
    )


async def put_file_from_url(url: str, key: str, retry: int = 3) -> None:
    key = (ROOT / key).as_posix()
    cos_client = new_client(retry)
    upload_id: str | None = None
    chunk_size = 4 * 1024 * 1024  # 4MB
    chunk_id = 1
    running_tasks = 0
    task_results = []

    async def put_chunk(chunk_id: int, chunk: bytes) -> None:
        nonlocal running_tasks

        res = await anyio.to_thread.run_sync(
            cos_client.upload_part, config.bucket, key, chunk, chunk_id, upload_id
        )
        task_results.append({"PartNumber": chunk_id, "ETag": res["ETag"]})
        running_tasks -= 1

    async with (
        anyio.create_task_group() as task_group,
        httpx.AsyncClient() as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()

        async for chunk in resp.aiter_bytes(chunk_size):
            while running_tasks >= 5:
                await anyio.lowlevel.checkpoint()

            if upload_id is None:
                if len(chunk) < chunk_size:
                    await anyio.to_thread.run_sync(
                        cos_client.upload_file_from_buffer,
                        config.bucket,
                        key,
                        chunk,
                    )
                    return
                upload_id = (
                    await anyio.to_thread.run_sync(
                        cos_client.create_multipart_upload, config.bucket, key
                    )
                )["UploadId"]

            task_group.start_soon(put_chunk, chunk_id, chunk)
            running_tasks += 1
            chunk_id += 1

    task_results.sort(key=lambda x: x["PartNumber"])
    try:
        await anyio.to_thread.run_sync(
            cos_client.complete_multipart_upload,
            config.bucket,
            key,
            upload_id,
            {"Part": task_results},
        )
    except Exception:
        await anyio.to_thread.run_sync(
            cos_client.abort_multipart_upload,
            config.bucket,
            key,
            upload_id,
        )
        raise
