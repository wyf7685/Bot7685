from datetime import datetime

import httpx
from nonebot import get_driver

from .config import plugin_config

_EXC_TYPES = (httpx.RequestError, httpx.HTTPStatusError)


class DetectorClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None
        self._api_available = False
        self._last_health_check = 0

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
            response = await self._get_client().get(
                plugin_config.health_endpoint, timeout=5
            )
            self._api_available = response.status_code == 200
        except _EXC_TYPES:
            self._api_available = False
        return self._api_available

    async def check_health(self) -> bool:
        if not plugin_config.api_base_url:
            return False
        now = datetime.now().timestamp()
        if now - self._last_health_check > 60:
            await self._check_health()
            self._last_health_check = now
        return self._api_available

    async def detect_screen(self, url: str) -> bool | None:
        if not self._api_available:
            return None
        try:
            response = await self._get_client().post(
                plugin_config.detect_endpoint,
                json={"url": url},
                timeout=10,
            )
            response.raise_for_status()
            result: dict[str, bool] = response.json()
            return result.get("is_screen", False)
        except _EXC_TYPES:
            self._api_available = False
            return None

    async def detect_screen_from_upload(
        self,
        file: bytes,
        extention: str,
        mime: str,
    ) -> bool | None:
        if not self._api_available:
            return None
        try:
            response = await self._get_client().post(
                plugin_config.detect_upload_endpoint,
                files={"file": (f"image.{extention}", file, mime)},
                timeout=30,
            )
            response.raise_for_status()
            result: dict[str, bool] = response.json()
            return result.get("is_screen", False)
        except _EXC_TYPES:
            self._api_available = False
            return None


detector_client = DetectorClient()
get_driver().on_shutdown(detector_client.close)
