import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from .client import AsyncS3Client
from .config import S3Config
from .exceptions import S3ConfigurationError


class S3Runtime:
    """Own shared S3 and source-download clients for one configuration."""

    def __init__(self, config: S3Config) -> None:
        self.config = config
        self.client = AsyncS3Client(config)
        self.source_client: httpx.AsyncClient | None = None
        self._state_lock = asyncio.Lock()
        self._close_task: asyncio.Task[None] | None = None
        self._started = False
        self._closing = False
        self._active_calls = 0
        self._drained = asyncio.Event()
        self._drained.set()

    @asynccontextmanager
    async def lease(self) -> AsyncIterator[S3Runtime]:
        async with self._state_lock:
            if self._closing:
                raise S3ConfigurationError
            await self._start_locked()
            self._active_calls += 1
            if self._active_calls == 1:
                self._drained.clear()
        try:
            yield self
        finally:
            async with self._state_lock:
                self._active_calls -= 1
                if self._active_calls == 0:
                    self._drained.set()

    async def _start_locked(self) -> None:
        if self._started:
            return
        try:
            await self.client.__aenter__()
            self.source_client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=float(self.config.timeout_seconds),
            )
        except BaseException:
            await self.client.aclose()
            self.source_client = None
            raise
        self._started = True

    def require_source_client(self) -> httpx.AsyncClient:
        if self.source_client is None:
            raise S3ConfigurationError
        return self.source_client

    async def aclose(self) -> None:
        async with self._state_lock:
            task = self._close_task
            if task is None:
                self._closing = True
                task = asyncio.create_task(self._drain_and_close())
                self._close_task = task
        await asyncio.shield(task)

    async def _drain_and_close(self) -> None:
        await self._drained.wait()
        errors: list[BaseException] = []
        source_client = self.source_client
        if source_client is not None:
            try:
                await source_client.aclose()
            except BaseException as error:
                errors.append(error)
            self.source_client = None
        try:
            await self.client.aclose()
        except BaseException as error:
            errors.append(error)
        self._started = False
        if errors:
            raise BaseExceptionGroup("failed to close S3 runtime", errors)


__all__ = ["S3Runtime"]
