import asyncio
from pathlib import Path

from nonebot_plugin_datastore import get_plugin_data
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


async def put_file(data: bytes, key: str, retry: int = 3):
    cache = get_plugin_data().cache_dir / str(id(data))
    await asyncio.to_thread(cache.write_bytes, data=data)

    try:
        await asyncio.to_thread(
            new_client(retry).upload_file,
            Bucket=config.bucket,
            Key=(ROOT / key).as_posix(),
            LocalFilePath=cache,
        )
    finally:
        await asyncio.to_thread(cache.unlink)


async def presign(key: str, expired: int = 3600):
    return await asyncio.to_thread(
        new_client().get_presigned_url,
        Bucket=config.bucket,
        Key=(ROOT / key).as_posix(),
        Method="GET",
        Expired=expired,
    )
