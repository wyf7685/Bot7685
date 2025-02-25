import functools
from collections.abc import Awaitable, Callable
from typing import Protocol

from .cos_ops import (
    DEFAULT_EXPIRE_SECS,
    presign,
    put_file,
    put_file_from_local,
    put_file_from_url,
)
from .database import update_key


class _WrappedCall[T](Protocol):
    async def __call__(
        self,
        _a0: T,
        /,
        key: str,
        expired: int = DEFAULT_EXPIRE_SECS,
    ) -> str: ...


def _wrap[T](call: Callable[[T, str], Awaitable[object]]) -> _WrappedCall[T]:
    @functools.wraps(call)
    async def wrapper(
        data: T,
        /,
        key: str,
        expired: int = DEFAULT_EXPIRE_SECS,
    ) -> str:
        await call(data, key)
        await update_key(key, expired)
        return await presign(key, expired)

    return wrapper


upload_from_buffer = _wrap(put_file)
upload_from_url = _wrap(put_file_from_url)
upload_from_local = _wrap(put_file_from_local)
