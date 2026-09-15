from typing import Any, overload

from pydantic import BaseModel

from src.service.cache import get_cache

DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60


class ForwardCacheItem(BaseModel):
    nick: str
    msg: list[dict[str, Any]]


_forward_cache = get_cache("group_pipe:value", list[ForwardCacheItem])
_message_id_cache = get_cache("group_pipe:message_id", str)


def _make_key(*parts: str) -> str:
    return "".join(f"{len(part)}:{part}" for part in parts)


async def set_forward_cache(
    adapter: str,
    forward_id: str,
    value: list[ForwardCacheItem],
    ttl: int | float | None = DEFAULT_CACHE_TTL,
) -> None:
    await _forward_cache.set(_make_key(adapter, forward_id), value, ttl=ttl)


async def get_forward_cache(
    adapter: str,
    forward_id: str,
) -> list[ForwardCacheItem] | None:
    return await _forward_cache.get(_make_key(adapter, forward_id))


async def set_msg_dst_id(
    src_adapter: str,
    src_id: str,
    dst_adapter: str,
    dst_id: str,
) -> None:
    await _message_id_cache.multi_set(
        {
            _make_key("src", src_adapter, dst_adapter, src_id): dst_id,
            _make_key("dst", src_adapter, dst_adapter, dst_id): src_id,
        },
        ttl=DEFAULT_CACHE_TTL,
    )


@overload
async def get_reply_id(
    src_adapter: str,
    dst_adapter: str,
    *,
    src_id: str,
) -> str | None: ...


@overload
async def get_reply_id(
    src_adapter: str,
    dst_adapter: str,
    *,
    dst_id: str,
) -> str | None: ...


async def get_reply_id(
    src_adapter: str,
    dst_adapter: str,
    src_id: str | None = None,
    dst_id: str | None = None,
) -> str | None:
    if src_id is not None:
        key = _make_key("src", src_adapter, dst_adapter, src_id)
    elif dst_id is not None:
        key = _make_key("dst", src_adapter, dst_adapter, dst_id)
    else:
        return None
    return await _message_id_cache.get(key)
