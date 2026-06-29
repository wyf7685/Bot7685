import asyncio
import contextlib
from collections.abc import AsyncIterator

from nonebot import logger
from nonebot.adapters import Adapter
from nonebot.drivers import (
    Driver,
    HTTPClientMixin,
    HTTPClientSession,
    Request,
    Response,
)

_ATTR_NAME = "_bot7685_adapter_session"
_IDLE_TIMEOUT = 300.0


class AdapterSession:
    def __init__(self, driver: Driver) -> None:
        self.session: HTTPClientSession | None = None
        self.active_requests_count: int = 0
        self._idle_timeout = _IDLE_TIMEOUT
        self._lock = asyncio.Lock()
        self._idle_close_task: asyncio.Task[None] | None = None
        self._shutdown = False
        driver.on_shutdown(self.close)

    async def _create_session(self, driver: HTTPClientMixin) -> HTTPClientSession:
        async with self._lock:
            if self._shutdown:
                raise RuntimeError("AdapterSession has been closed")

            if self._idle_close_task is not None:
                self._idle_close_task.cancel()
                self._idle_close_task = None

            if self.session is None:
                logger.debug("Creating new HTTP client session")
                self.session = driver.get_session()
                await self.session.setup()

            self.active_requests_count += 1
            return self.session

    def _start_idle_close_task(self) -> None:
        if self._idle_close_task is None or self._idle_close_task.done():
            self._idle_close_task = asyncio.create_task(self._close_when_idle())

    async def _close_when_idle(self) -> None:
        try:
            await asyncio.sleep(self._idle_timeout)
            async with self._lock:
                if self.active_requests_count != 0 or self.session is None:
                    return

                session = self.session
                self.session = None

            logger.debug("Closing idle HTTP client session")
            await session.close()
        finally:
            async with self._lock:
                if self._idle_close_task is asyncio.current_task():
                    self._idle_close_task = None

    @contextlib.asynccontextmanager
    async def get_session(
        self, driver: HTTPClientMixin
    ) -> AsyncIterator[HTTPClientSession]:
        session = await self._create_session(driver)
        try:
            yield session
        finally:
            async with self._lock:
                if self.active_requests_count > 0:
                    self.active_requests_count -= 1

                if not self._shutdown and self.active_requests_count == 0:
                    logger.debug("No active requests, starting idle close task")
                    self._start_idle_close_task()

    async def close(self) -> None:
        async with self._lock:
            self._shutdown = True

        task = self._idle_close_task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        async with self._lock:
            session = self.session
            self.session = None

        if session is not None:
            await session.close()


async def request(self: Adapter, setup: Request) -> Response:
    if not isinstance(self.driver, HTTPClientMixin):
        raise TypeError("Current driver does not support http client")

    adapter_session: AdapterSession
    if hasattr(self, _ATTR_NAME):
        adapter_session = getattr(self, _ATTR_NAME)
    else:
        adapter_session = AdapterSession(self.driver)
        setattr(self, _ATTR_NAME, adapter_session)

    async with adapter_session.get_session(self.driver) as session:
        return await session.request(setup)


for adapter in Adapter.__subclasses__():
    adapter.request = request
