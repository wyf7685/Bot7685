import asyncio
from pathlib import Path

from nonebot_plugin_datastore import get_plugin_data
from qcloud_cos import CosConfig, CosS3Client
from qcloud_cos.cos_exception import CosClientError, CosServiceError

from .config import config

ROOT = Path("qbot/upload")

def new_client() -> CosS3Client:
    return CosS3Client(
        CosConfig(
            Region=config.region,
            SecretId=config.secret_id,
            SecretKey=config.secret_key,
            Token=None,
            Scheme="https",
        )
    )


async def put_file(data: bytes, key: str, max_try: int = 3):
    cache = get_plugin_data().cache_dir / str(id(data))
    cache.write_bytes(data)

    err = None
    for _ in range(max_try):
        try:
            await asyncio.to_thread(
                new_client().upload_file,
                Bucket=config.bucket,
                Key=(ROOT / key).as_posix(),
                LocalFilePath=cache,
            )
            cache.unlink()
            return
        except CosClientError or CosServiceError as e:
            err = e
    cache.unlink()
    if err is not None:
        raise err


async def presign(key: str, expired: int = 3600):
    return await asyncio.to_thread(
        new_client().get_presigned_url,
        Bucket=config.bucket,
        Key=(ROOT / key).as_posix(),
        Method="GET",
        Expired=expired,
    )
