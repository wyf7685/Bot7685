import contextlib
import functools
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable
from datetime import UTC, datetime
from typing import Concatenate

import httpx
from nonebot import get_driver, logger
from pydantic import BaseModel

from .config import plugin_config


class Endpoints:
    def __init__(self) -> None:
        self._base_url = plugin_config.api_base_url

    @property
    def available(self) -> bool:
        return self._base_url is not None

    @property
    def _base(self) -> str:
        if self._base_url is None:
            raise ValueError("API base URL is not set.")
        return self._base_url.rstrip("/")

    @property
    def health(self) -> str:
        return f"{self._base}/health"

    @property
    def detect(self) -> str:
        return f"{self._base}/detect"

    @property
    def detect_upload(self) -> str:
        return f"{self._base}/detect/upload"

    @property
    def classify(self) -> str:
        return f"{self._base}/classify"

    @property
    def package(self) -> str:
        return f"{self._base}/package"


class DetectResult(BaseModel):
    image_id: str
    is_screen: bool


def _check_api[**P, R](
    method: Callable[Concatenate[DetectorClient, P], Awaitable[R]],
) -> Callable[Concatenate[DetectorClient, P], Awaitable[R | None]]:
    @functools.wraps(method)
    async def wrapper(
        self: DetectorClient,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R | None:
        if not await self.check_health():
            return None
        try:
            result = await method(self, *args, **kwargs)
        except httpx.RequestError:
            self._mark_api_status(False)
            return None
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = None
            logger.warning(
                f"API request failed with {exc.response.status_code}: {exc!r}"
                f"{f"\nDetail: {detail}" if detail else ""}"
            )

            return None
        self._mark_api_status(True)
        return result

    return wrapper


def _check_api_gen[**P, R](
    method: Callable[Concatenate[DetectorClient, P], AsyncGenerator[R]],
) -> Callable[Concatenate[DetectorClient, P], AsyncGenerator[R]]:
    @functools.wraps(method)
    async def wrapper(
        self: DetectorClient,
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> AsyncGenerator[R]:
        if not await self.check_health():
            return
        try:
            async for item in method(self, *args, **kwargs):
                yield item
        except httpx.RequestError:
            self._mark_api_status(False)
            raise
        except httpx.HTTPStatusError as exc:
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = None
            logger.warning(
                f"API request failed with {exc.response.status_code}: {exc!r}"
                f"{f"\nDetail: {detail}" if detail else ""}"
            )
            raise
        self._mark_api_status(True)

    return wrapper


class DetectorClient:
    def __init__(self) -> None:
        self.endpoints = Endpoints()
        self._client: httpx.AsyncClient | None = None
        self._api_available = False
        self._last_health_check = datetime.fromtimestamp(0, tz=UTC)

    @property
    def is_available(self) -> bool:
        return self.endpoints.available and self._api_available

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _check_health(self) -> bool:
        try:
            response = await self._get_client().get(self.endpoints.health, timeout=5)
        except httpx.RequestError, httpx.HTTPStatusError:
            return False
        else:
            return response.status_code == 200

    def _mark_api_status(self, available: bool) -> None:
        self._api_available = available
        self._last_health_check = datetime.now(tz=UTC)

    async def check_health(self) -> bool:
        if not self.endpoints.available:
            return False
        if (datetime.now(tz=UTC) - self._last_health_check).total_seconds() > 60:
            available = await self._check_health()
            self._mark_api_status(available)
        return self.is_available

    @_check_api
    async def detect_screen(self, url: str) -> DetectResult:
        response = await self._get_client().post(
            self.endpoints.detect,
            json={"url": url},
            timeout=10,
        )
        response.raise_for_status()
        return DetectResult.model_validate_json(response.content)

    @_check_api
    async def detect_screen_from_upload(
        self,
        file: bytes,
        extention: str,
        mime: str,
    ) -> DetectResult:
        response = await self._get_client().post(
            self.endpoints.detect_upload,
            files={"file": (f"image.{extention}", file, mime)},
            timeout=30,
        )
        response.raise_for_status()
        return DetectResult.model_validate_json(response.content)

    @_check_api
    async def classify(self, image_id: str, is_screen: bool) -> None:
        await self._get_client().post(
            self.endpoints.classify,
            json={"image_id": image_id, "is_screen": is_screen},
            timeout=5,
        )

    @_check_api_gen
    async def package(self, after: datetime) -> AsyncGenerator[bytes]:
        async with self._get_client().stream(
            "POST",
            self.endpoints.package,
            json={"after_timestamp": after.isoformat()},
            timeout=30,
        ) as response:
            response.raise_for_status()
            async for chunk in response.aiter_bytes():
                yield chunk


detector_client = DetectorClient()
get_driver().on_shutdown(detector_client.close)


@contextlib.asynccontextmanager
async def calc_stream_size(
    stream: AsyncIterable[bytes],
) -> AsyncGenerator[tuple[AsyncGenerator[bytes], Callable[[], int]]]:
    size = 0

    def get_size() -> int:
        return size

    async def wrapper() -> AsyncGenerator[bytes]:
        nonlocal size
        async for chunk in stream:
            size += len(chunk)
            yield chunk

    yield wrapper(), get_size
