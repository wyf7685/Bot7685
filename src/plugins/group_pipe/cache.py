from typing import overload

from src.service.cache import get_cache

DEFAULT_CACHE_TTL = 7 * 24 * 60 * 60

_value_cache = get_cache("group_pipe:value", str)
_message_id_cache = get_cache("group_pipe:message_id", str)


def _make_key(*parts: str) -> str:
    return "".join(f"{len(part)}:{part}" for part in parts)


async def set_cache_value(
    adapter: str,
    key: str,
    value: str,
    ttl: int | float | None = DEFAULT_CACHE_TTL,
) -> None:
    await _value_cache.set(_make_key(adapter, key), value, ttl=ttl)


async def get_cache_value(adapter: str, key: str) -> str | None:
    return await _value_cache.get(_make_key(adapter, key))


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
