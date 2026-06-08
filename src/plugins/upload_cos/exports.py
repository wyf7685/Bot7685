import pathlib
from typing import assert_never, overload

import anyio

from .cos_ops import (
    DEFAULT_TTL_SECS,
    presign,
    put_file_from_buffer,
    put_file_from_local,
    put_file_from_url,
)
from .database import update_key


@overload
async def upload_cos(
    data: bytes,
    /,
    key: str,
    ttl: int = ...,
) -> str: ...
@overload
async def upload_cos(
    url: str,
    /,
    key: str,
    ttl: int = ...,
) -> str: ...
@overload
async def upload_cos(
    path: pathlib.Path | anyio.Path,
    /,
    key: str,
    ttl: int = ...,
) -> str: ...


async def upload_cos(
    source: bytes | str | pathlib.Path | anyio.Path,
    key: str,
    ttl: int = DEFAULT_TTL_SECS,
) -> str:
    match source:
        case bytes():
            await put_file_from_buffer(source, key)
        case str():
            await put_file_from_url(source, key)
        case pathlib.Path():
            await put_file_from_local(source, key)
        case anyio.Path():
            await put_file_from_local(pathlib.Path(source), key)
        case _:
            assert_never(source)

    await update_key(key, ttl)
    return await presign(key, ttl)
