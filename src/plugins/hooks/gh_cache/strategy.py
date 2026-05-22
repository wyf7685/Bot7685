import datetime
from datetime import timedelta
from typing import NoReturn, cast, override

import nonebot
from githubkit.cache.base import AsyncBaseCache, BaseCacheStrategy
from githubkit.exception import CacheUnsupportedError
from hishel import AsyncBaseStorage, JSONSerializer, Metadata
from httpcore import Request, Response
from nonebot.adapters.github import Bot as GitHubBot

nonebot.require("src.service.cache")
from src.service.cache import Cache, get_cache

__all__ = ["AsyncBotCacheStrategy", "GitHubBot"]

HISHEL_CACHE_TTL = timedelta(days=7)


class AsyncBotCache(AsyncBaseCache):
    def __init__(self, cache: Cache[str]) -> None:
        self._cache = cache

    @override
    async def aget(self, key: str) -> str | None:
        return await self._cache.get(key)

    @override
    async def aset(self, key: str, value: str, ex: timedelta) -> None:
        await self._cache.set(key, value, ex)


class AsyncBotStorage(AsyncBaseStorage):
    def __init__(self, cache: Cache[str]) -> None:
        self._cache = cache
        self._serializer = JSONSerializer()

    def _serialize(
        self, response: Response, request: Request, metadata: Metadata
    ) -> str:
        data = self._serializer.dumps(
            response=response, request=request, metadata=metadata
        )
        return cast("str", data)  # JSONSerializer.dumps() always returns str

    @override
    async def store(
        self,
        key: str,
        response: Response,
        request: Request,
        metadata: Metadata | None = None,
    ) -> None:
        metadata = metadata or Metadata(
            cache_key=key,
            created_at=datetime.datetime.now(datetime.UTC),
            number_of_uses=0,
        )
        value = self._serialize(response, request, metadata)
        await self._cache.set(key, value, HISHEL_CACHE_TTL)

    @override
    async def remove(self, key: str | Response) -> None:
        if isinstance(key, Response):
            key = cast("str", key.extensions["cache_metadata"]["cache_key"])
        await self._cache.delete(key)

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
        return self._serializer.loads(data) if data is not None else None

    @override
    async def aclose(self) -> None:
        return  # cache is managed by src.service.cache


class AsyncBotCacheStrategy(BaseCacheStrategy):
    def __init__(self, namespace: str) -> None:
        self._cache = get_cache(f"{namespace}:cache", str)
        self._hishel_cache = get_cache(f"{namespace}:hishel", str)

    @override
    def get_cache_storage(self) -> NoReturn:
        raise CacheUnsupportedError("AsyncBotCacheStrategy does not support sync usage")

    @override
    def get_async_cache_storage(self) -> AsyncBaseCache:
        return AsyncBotCache(self._cache)

    @override
    def get_hishel_storage(self) -> NoReturn:
        raise CacheUnsupportedError("AsyncBotCacheStrategy does not support sync usage")

    @override
    def get_async_hishel_storage(self) -> AsyncBaseStorage:
        return AsyncBotStorage(self._hishel_cache)
