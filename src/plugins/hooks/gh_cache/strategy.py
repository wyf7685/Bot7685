import asyncio
import concurrent.futures
import datetime
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import cast, override

import anyio
import nonebot
from githubkit.cache.base import AsyncBaseCache, BaseCache, BaseCacheStrategy
from githubkit.exception import CacheUnsupportedError
from hishel import AsyncBaseStorage, BaseStorage, JSONSerializer, Metadata
from httpcore import Request, Response
from nonebot.adapters.github import Bot as GitHubBot

nonebot.require("src.service.cache")
nonebot.require("src.service.task")
from src.service.cache import Cache, get_cache
from src.service.task import call_soon

__all__ = ["AsyncBotCacheStrategy", "GitHubBot"]

HISHEL_CACHE_TTL = timedelta(days=7)


def _call_coro_from_thread[*Ts, R](
    call: Callable[[*Ts], Awaitable[R]],
    *args: *Ts,
) -> R:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise CacheUnsupportedError(
            "Cannot call sync cache strategy from an async context"
        )

    fut = concurrent.futures.Future()

    async def wrapper() -> None:
        try:
            result = await call(*args)
        except Exception as e:
            fut.set_exception(e)
        except anyio.get_cancelled_exc_class():
            fut.cancel()
        else:
            fut.set_result(result)

    call_soon(wrapper)
    return fut.result()


class BotCacheHolder[T]:
    def __init__(self, cache: Cache[T]) -> None:
        self._cache = cache


class SyncBotCache(BaseCache, BotCacheHolder[str]):
    @override
    def get(self, key: str) -> str | None:
        return _call_coro_from_thread(self._cache.get, key)

    @override
    def set(self, key: str, value: str, ex: timedelta) -> None:
        _call_coro_from_thread(self._cache.set, key, value, ex)


class AsyncBotCache(AsyncBaseCache, BotCacheHolder[str]):
    @override
    async def aget(self, key: str) -> str | None:
        return await self._cache.get(key)

    @override
    async def aset(self, key: str, value: str, ex: timedelta) -> None:
        await self._cache.set(key, value, ex)


class BotCacheStorage(BotCacheHolder[str]):
    def __init__(self, cache: Cache[str]) -> None:
        super().__init__(cache=cache)
        self._serializer = JSONSerializer()

    def _serialize(
        self, response: Response, request: Request, metadata: Metadata
    ) -> str:
        data = self._serializer.dumps(
            response=response, request=request, metadata=metadata
        )
        return cast("str", data)  # JSONSerializer.dumps() always returns str

    def _deserialize(self, data: str) -> tuple[Response, Request, Metadata]:
        return self._serializer.loads(data)

    def _new_metadata(self, key: str) -> Metadata:
        return Metadata(
            cache_key=key,
            created_at=datetime.datetime.now(datetime.UTC),
            number_of_uses=0,
        )

    def _normalize_key(self, key: str | Response) -> str:
        if isinstance(key, Response):
            return cast("str", key.extensions["cache_metadata"]["cache_key"])
        return key


class SyncBotStorage(BotCacheStorage, BaseStorage):
    @override
    def store(
        self,
        key: str,
        response: Response,
        request: Request,
        metadata: Metadata | None = None,
    ) -> None:
        value = self._serialize(response, request, metadata or self._new_metadata(key))
        _call_coro_from_thread(self._cache.set, key, value, HISHEL_CACHE_TTL)

    @override
    def remove(self, key: str | Response) -> None:
        _call_coro_from_thread(self._cache.delete, self._normalize_key(key))

    @override
    def update_metadata(
        self,
        key: str,
        response: Response,
        request: Request,
        metadata: Metadata,
    ) -> None:
        ttl = _call_coro_from_thread(self._cache.pttl, key)
        if ttl < 0:
            self.store(key, response, request, metadata)
        else:
            value = self._serialize(response, request, metadata)
            _call_coro_from_thread(self._cache.set, key, value, ttl)

    @override
    def retrieve(self, key: str) -> tuple[Response, Request, Metadata] | None:
        data = _call_coro_from_thread(self._cache.get, key)
        return self._deserialize(data) if data is not None else None

    @override
    def close(self) -> None:
        return  # cache is managed by src.service.cache


class AsyncBotStorage(BotCacheStorage, AsyncBaseStorage):
    @override
    async def store(
        self,
        key: str,
        response: Response,
        request: Request,
        metadata: Metadata | None = None,
    ) -> None:
        value = self._serialize(response, request, metadata or self._new_metadata(key))
        await self._cache.set(key, value, HISHEL_CACHE_TTL)

    @override
    async def remove(self, key: str | Response) -> None:
        await self._cache.delete(self._normalize_key(key))

    @override
    async def update_metadata(
        self,
        key: str,
        response: Response,
        request: Request,
        metadata: Metadata,
    ) -> None:
        ttl = await self._cache.pttl(key)
        if ttl < 0:
            await self.store(key, response, request, metadata)
        else:
            value = self._serialize(response, request, metadata)
            await self._cache.set(key, value, ttl)

    @override
    async def retrieve(self, key: str) -> tuple[Response, Request, Metadata] | None:
        data = await self._cache.get(key)
        return self._deserialize(data) if data is not None else None

    @override
    async def aclose(self) -> None:
        return  # cache is managed by src.service.cache


class AsyncBotCacheStrategy(BaseCacheStrategy):
    def __init__(self, namespace: str) -> None:
        self._cache = get_cache(f"{namespace}:cache", str)
        self._hishel_cache = get_cache(f"{namespace}:hishel", str)

    @override
    def get_cache_storage(self) -> BaseCache:
        return SyncBotCache(self._cache)

    @override
    def get_async_cache_storage(self) -> AsyncBaseCache:
        return AsyncBotCache(self._cache)

    @override
    def get_hishel_storage(self) -> BaseStorage:
        return SyncBotStorage(self._hishel_cache)

    @override
    def get_async_hishel_storage(self) -> AsyncBaseStorage:
        return AsyncBotStorage(self._hishel_cache)
