from collections.abc import AsyncIterable, Buffer
from os import PathLike
from pathlib import Path
from typing import assert_never, cast, overload

from .cos_ops import (
    DEFAULT_TTL_SECS,
    presign,
    put_file_from_aiterable,
    put_file_from_buffer,
    put_file_from_local,
    put_file_from_url,
)
from .database import update_key


@overload
async def upload_cos(data: Buffer, /, key: str, ttl: int = ...) -> str: ...
@overload
async def upload_cos(url: str, /, key: str, ttl: int = ...) -> str: ...
@overload
async def upload_cos(path: PathLike[str], /, key: str, ttl: int = ...) -> str: ...
@overload
async def upload_cos(
    stream: AsyncIterable[bytes], /, key: str, ttl: int = ...
) -> str: ...


async def upload_cos(
    source: Buffer | str | PathLike[str] | AsyncIterable[bytes],
    key: str,
    ttl: int = DEFAULT_TTL_SECS,
) -> str:
    match source:
        case Buffer():
            await put_file_from_buffer(source, key)
        case str() if source.startswith(("http://", "https://")):
            await put_file_from_url(source, key)
        case str():
            raise ValueError(f"Invalid URL: {source}")
        case PathLike():
            await put_file_from_local(Path(cast("PathLike[str]", source)), key)
        case AsyncIterable():
            await put_file_from_aiterable(source, key)
        case _:
            assert_never(source)

    await update_key(key, ttl)
    return await presign(key, ttl)
