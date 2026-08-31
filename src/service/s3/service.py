import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import Lock

from nonebot import get_driver, logger
from pydantic import ValidationError

from .client import HeadObjectOutput
from .config import S3Config
from .exceptions import (
    S3ConfigurationConflictError,
    S3ConfigurationError,
    S3ConfigurationInUseError,
)
from .repository import S3ConfigRepository
from .retention import (
    forget_temporary_object,
    has_temporary_objects,
    list_expired_objects,
    record_temporary_object,
)
from .runtime import S3Runtime
from .transfer import UploadSource, upload_source


@dataclass(frozen=True, slots=True)
class S3ConfigurationSnapshot:
    revision: int
    config: S3Config | None
    load_error: bool


@dataclass(frozen=True, slots=True)
class _ServiceState:
    config: S3Config
    runtime: S3Runtime


class S3Service:
    """Process-local S3 service with atomically replaceable configuration."""

    def __init__(self) -> None:
        self._repository = S3ConfigRepository()
        self._state_lock = asyncio.Lock()
        self._revision = 0
        self._load_error = False
        self._shutdown = False
        self._retired_runtimes: set[asyncio.Task[None]] = set()
        self._state: _ServiceState | None = None
        try:
            config = self._repository.load()
            if config is not None:
                self._state = self._build_state(config)
        except (OSError, ValidationError, ValueError) as error:
            self._load_error = True
            logger.error(
                f"S3 persisted configuration is unavailable: {type(error).__name__}"
            )

    @staticmethod
    def _build_state(config: S3Config) -> _ServiceState:
        return _ServiceState(config=config, runtime=S3Runtime(config))

    async def configuration_snapshot(self) -> S3ConfigurationSnapshot:
        async with self._state_lock:
            return S3ConfigurationSnapshot(
                revision=self._revision,
                config=self._state.config if self._state is not None else None,
                load_error=self._load_error,
            )

    async def replace_configuration(
        self,
        config: S3Config,
        *,
        expected_revision: int,
    ) -> int:
        candidate = self._build_state(config)
        try:
            async with self._state_lock:
                self._ensure_open()
                if expected_revision != self._revision:
                    raise S3ConfigurationConflictError
                previous = self._state
                if (
                    previous is not None
                    and previous.config.namespace_identity != config.namespace_identity
                    and await has_temporary_objects(previous.config.namespace_identity)
                ):
                    raise S3ConfigurationInUseError
                try:
                    self._repository.save(config)
                except OSError as error:
                    raise S3ConfigurationError(cause=error) from error
                self._state = candidate
                self._load_error = False
                self._revision += 1
                revision = self._revision
        except BaseException:
            await candidate.runtime.aclose()
            raise

        if previous is not None:
            self._retire_runtime(previous.runtime)
        return revision

    async def reset_configuration(self, *, expected_revision: int) -> int:
        async with self._state_lock:
            self._ensure_open()
            if expected_revision != self._revision:
                raise S3ConfigurationConflictError
            previous = self._state
            if previous is not None and await has_temporary_objects(
                previous.config.namespace_identity
            ):
                raise S3ConfigurationInUseError
            try:
                self._repository.delete()
            except OSError as error:
                raise S3ConfigurationError(cause=error) from error
            self._state = None
            self._load_error = False
            self._revision += 1
            revision = self._revision

        if previous is not None:
            self._retire_runtime(previous.runtime)
        return revision

    @asynccontextmanager
    async def _lease_runtime(
        self,
    ) -> AsyncIterator[tuple[S3Config, S3Runtime]]:
        stack = AsyncExitStack()
        try:
            async with self._state_lock:
                self._ensure_open()
                state = self._require_state()
                runtime = await stack.enter_async_context(state.runtime.lease())
                config = state.config
            yield config, runtime
        finally:
            await stack.aclose()

    async def upload(self, source: UploadSource, *, key: str) -> None:
        async with self._lease_runtime() as (config, runtime):
            object_key = self._object_key(config, key)
            await upload_source(runtime, source, key=object_key)

    async def upload_temporary(
        self,
        source: UploadSource,
        *,
        key: str,
        expires_in: int,
    ) -> str:
        self._validate_expiration(expires_in)
        async with self._lease_runtime() as (config, runtime):
            object_key = self._object_key(config, key)
            await upload_source(runtime, source, key=object_key)
            await record_temporary_object(
                namespace=config.namespace_identity,
                key=object_key,
                expires_in=expires_in,
            )
            return runtime.client.presign_url(
                object_key,
                method="GET",
                expires_in=expires_in,
            )

    async def presign_get(self, *, key: str, expires_in: int) -> str:
        self._validate_expiration(expires_in)
        async with self._lease_runtime() as (config, runtime):
            return runtime.client.presign_url(
                self._object_key(config, key),
                method="GET",
                expires_in=expires_in,
            )

    async def delete(self, *, key: str) -> None:
        async with self._lease_runtime() as (config, runtime):
            await runtime.client.delete_object(self._object_key(config, key))

    async def head(self, *, key: str) -> HeadObjectOutput | None:
        async with self._lease_runtime() as (config, runtime):
            return await runtime.client.head_object(self._object_key(config, key))

    async def get(self, *, key: str) -> bytes:
        async with self._lease_runtime() as (config, runtime):
            return await runtime.client.get_object(self._object_key(config, key))

    async def stream_get(
        self,
        *,
        key: str,
        offset: int = 0,
    ) -> AsyncIterator[bytes]:
        if offset < 0:
            raise ValueError("offset must not be negative")
        async with self._lease_runtime() as (config, runtime):
            object_key = self._object_key(config, key)
            async with runtime.client.stream_get(
                object_key,
                range_start=offset or None,
            ) as response:
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def ping(self) -> bool:
        async with self._lease_runtime() as (config, runtime):
            try:
                objects = runtime.client.list_objects(
                    prefix=config.key_prefix or None,
                    delimiter=None,
                    max_keys=1,
                )
                async with contextlib.aclosing(objects):
                    await anext(objects, None)
            except Exception:
                return False
            return True

    async def cleanup_expired(self) -> None:
        expired = await list_expired_objects()
        if not expired:
            return
        async with self._lease_runtime() as (config, runtime):
            namespace = config.namespace_identity
            for item in expired:
                if item.namespace != namespace:
                    continue
                try:
                    await runtime.client.delete_object(item.key)
                except Exception as error:
                    logger.opt(exception=error).warning(
                        f"Failed to delete expired S3 object: {item.key}"
                    )
                    continue
                await forget_temporary_object(
                    namespace=item.namespace,
                    key=item.key,
                )

    async def aclose(self) -> None:
        async with self._state_lock:
            if self._shutdown:
                return
            self._shutdown = True
            state = self._state
            self._state = None
        if state is not None:
            await self._close_runtime(state.runtime)
        retired = tuple(self._retired_runtimes)
        if retired:
            await asyncio.gather(*retired, return_exceptions=True)

    def _ensure_open(self) -> None:
        if self._shutdown:
            raise S3ConfigurationError

    def _require_state(self) -> _ServiceState:
        if self._state is None:
            raise S3ConfigurationError
        return self._state

    def _retire_runtime(self, runtime: S3Runtime) -> None:
        task = asyncio.create_task(self._close_runtime(runtime))
        self._retired_runtimes.add(task)
        task.add_done_callback(self._retired_runtimes.discard)

    @staticmethod
    async def _close_runtime(runtime: S3Runtime) -> None:
        try:
            await runtime.aclose()
        except Exception as error:
            logger.warning(f"Failed to close an S3 runtime: {type(error).__name__}")

    @staticmethod
    def _validate_expiration(expires_in: int) -> None:
        if not 1 <= expires_in <= 604800:
            raise ValueError("expires_in must be between 1 and 604800 seconds")

    @staticmethod
    def _object_key(config: S3Config, key: str) -> str:
        normalized = key.strip("/")
        if not normalized:
            raise ValueError("key must not be empty")
        if "\x00" in normalized:
            raise ValueError("key must not contain NUL")
        if any(part in {".", ".."} for part in normalized.split("/")):
            raise ValueError("key must not contain dot path components")
        if not config.key_prefix:
            return normalized
        return (PurePosixPath(config.key_prefix) / normalized).as_posix()


_service: S3Service | None = None
_service_lock = Lock()
_service_shutdown_started = False


def get_s3_service() -> S3Service:
    global _service
    with _service_lock:
        if _service_shutdown_started:
            raise S3ConfigurationError
        if _service is None:
            _service = S3Service()
        return _service


@get_driver().on_shutdown
async def _close_s3_service() -> None:
    global _service_shutdown_started
    with _service_lock:
        _service_shutdown_started = True
        service = _service
    if service is not None:
        await service.aclose()


__all__ = ["S3ConfigurationSnapshot", "S3Service", "get_s3_service"]
