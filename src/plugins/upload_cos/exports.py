from pathlib import Path

from .cos_ops import presign, put_file, put_file_from_local, put_file_from_url
from .database import update_key


async def upload_from_buffer(data: bytes, key: str, expired: int = 3600) -> str:
    await put_file(data, key)
    await update_key(key, expired)
    return await presign(key, expired)


async def upload_from_url(url: str, key: str, expired: int = 3600) -> str:
    await put_file_from_url(url, key)
    await update_key(key, expired)
    return await presign(key, expired)


async def upload_from_local(path: Path, key: str, expired: int = 3600) -> str:
    await put_file_from_local(path, key)
    await update_key(key, expired)
    return await presign(key, expired)
