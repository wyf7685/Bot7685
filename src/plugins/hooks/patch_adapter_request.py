import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import nonebot
from nonebot import logger
from nonebot.adapters import Adapter
from nonebot.drivers import (
    Driver,
    HTTPClientMixin,
    HTTPClientSession,
    HTTPVersion,
    Request,
    Response,
)

from src.utils import copy_signature

from ._http_request import preprocess_request

_ATTR_NAME = "_bot7685_adapter_session"
_IDLE_TIMEOUT = 300.0

type _SessionKey = tuple[HTTPVersion, str | None]


@dataclass(slots=True)
class _SessionState:
    session: HTTPClientSession
    active_requests_count: int = 0
    idle_close_task: asyncio.Task[None] | None = None


class AdapterSession:
    def __init__(self, driver: Driver) -> None:
        self._sessions: dict[_SessionKey, _SessionState] = {}
        self.active_requests_count = 0
        self._idle_timeout = _IDLE_TIMEOUT
        self._lock = asyncio.Lock()
        self._idle_close_tasks: set[asyncio.Task[None]] = set()
        self._drained = asyncio.Event()
        self._drained.set()
        self._close_task: asyncio.Task[None] | None = None
        self._shutdown = False
        driver.on_shutdown(self.close)

    async def _acquire_session(
        self,
        driver: HTTPClientMixin,
        setup: Request,
    ) -> tuple[_SessionKey, _SessionState]:
        key = (setup.version, setup.proxy)
        async with self._lock:
            if self._shutdown:
                raise RuntimeError("AdapterSession has been closed")

            state = self._sessions.get(key)
            if state is None:
                logger.debug("Creating new HTTP client session")
                session = driver.get_session(
                    version=setup.version,
                    proxy=setup.proxy,
                )
                try:
                    await session.setup()
                except BaseException:
                    with contextlib.suppress(Exception):
                        await asyncio.shield(session.close())
                    raise
                state = _SessionState(session)
                self._sessions[key] = state
            elif state.idle_close_task is not None:
                state.idle_close_task.cancel()
                state.idle_close_task = None

            state.active_requests_count += 1
            self.active_requests_count += 1
            if self.active_requests_count == 1:
                self._drained.clear()
            return key, state

    def _start_idle_close_task(
        self,
        key: _SessionKey,
        state: _SessionState,
    ) -> None:
        if state.idle_close_task is None or state.idle_close_task.done():
            task = asyncio.create_task(
                self._close_when_idle(key, state),
                name="adapter-session-idle-close",
            )
            state.idle_close_task = task
            self._idle_close_tasks.add(task)
            task.add_done_callback(self._idle_close_tasks.discard)

    async def _close_when_idle(
        self,
        key: _SessionKey,
        state: _SessionState,
    ) -> None:
        try:
            await asyncio.sleep(self._idle_timeout)
            async with self._lock:
                if (
                    self._shutdown
                    or self._sessions.get(key) is not state
                    or state.active_requests_count != 0
                ):
                    return
                del self._sessions[key]
                state.idle_close_task = None

            logger.debug("Closing idle HTTP client session")
            await state.session.close()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.opt(exception=exc).error("Failed to close idle HTTP client session")

    async def _release_session(
        self,
        key: _SessionKey,
        state: _SessionState,
    ) -> None:
        async with self._lock:
            state.active_requests_count -= 1
            self.active_requests_count -= 1
            if self.active_requests_count == 0:
                self._drained.set()

            if (
                not self._shutdown
                and state.active_requests_count == 0
                and self._sessions.get(key) is state
            ):
                logger.debug("No active requests, starting idle close task")
                self._start_idle_close_task(key, state)

    @contextlib.asynccontextmanager
    async def get_session(
        self,
        driver: HTTPClientMixin,
        setup: Request,
    ) -> AsyncGenerator[HTTPClientSession]:
        key, state = await self._acquire_session(driver, setup)
        try:
            yield state.session
        finally:
            await self._release_session(key, state)

    async def _drain_and_close_sessions(self) -> None:
        await self._drained.wait()
        async with self._lock:
            states = tuple(self._sessions.values())
            self._sessions.clear()
            idle_close_tasks = tuple(self._idle_close_tasks)

        if idle_close_tasks:
            await asyncio.gather(*idle_close_tasks, return_exceptions=True)

        results = await asyncio.gather(
            *(state.session.close() for state in states),
            return_exceptions=True,
        )
        if exceptions := [
            result for result in results if isinstance(result, BaseException)
        ]:
            raise BaseExceptionGroup(
                "one or more adapter HTTP sessions failed to close",
                exceptions,
            )

    async def close(self) -> None:
        async with self._lock:
            task = self._close_task
            if task is None:
                self._shutdown = True
                for state in self._sessions.values():
                    if state.idle_close_task is not None:
                        state.idle_close_task.cancel()
                        state.idle_close_task = None
                task = asyncio.create_task(
                    self._drain_and_close_sessions(),
                    name="adapter-session-close",
                )
                self._close_task = task

        await asyncio.shield(task)


async def request(self: Adapter, setup: Request) -> Response:
    if not isinstance(self.driver, HTTPClientMixin):
        raise TypeError("Current driver does not support http client")

    preprocess_request(self.driver, setup)

    adapter_session: AdapterSession
    if hasattr(self, _ATTR_NAME):
        adapter_session = getattr(self, _ATTR_NAME)
    else:
        adapter_session = AdapterSession(self.driver)
        setattr(self, _ATTR_NAME, adapter_session)

    async with adapter_session.get_session(self.driver, setup) as session:
        return await session.request(setup)


for adapter_type in {type(adapter) for adapter in nonebot.get_adapters().values()}:
    original_request = next(
        cls.__dict__["request"]
        for cls in adapter_type.__mro__
        if "request" in cls.__dict__
    )
    if original_request is not Adapter.request:
        logger.warning(
            f"Skipping HTTP session patch for {adapter_type.__module__}."
            f"{adapter_type.__name__}: custom request implementation"
        )
        continue
    adapter_type.request = copy_signature(Adapter.request)(request)
