from pathlib import Path
from typing import overload

from .cos_ops import (
    DEFAULT_EXPIRE_SECS,
    presign,
    put_file,
    put_file_from_local,
    put_file_from_url,
)
from .database import update_key


@overload
async def upload_cos(
    data: bytes,
    /,
    key: str,
    expired: int = ...,
) -> str: ...
@overload
async def upload_cos(
    url: str,
    /,
    key: str,
    expired: int = ...,
) -> str: ...
@overload
async def upload_cos(
    path: Path,
    /,
    key: str,
    expired: int = ...,
) -> str: ...


async def upload_cos(
    source: bytes | str | Path,
    key: str,
    expired: int = DEFAULT_EXPIRE_SECS,
) -> str:
    match source:
        case bytes():
            await put_file(source, key)
        case str():
            await put_file_from_url(source, key)
        case Path():
            await put_file_from_local(source, key)
        case _:
            raise TypeError(f"unsupported source type: {type(source)}")

    await update_key(key, expired)
    return await presign(key, expired)
