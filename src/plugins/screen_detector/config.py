import functools

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class PluginConfig(BaseModel):
    enabled_scenes: set[str] = Field(default_factory=set)
    api_base_url: str | None = Field(default=None)

    @property
    def _base_url(self) -> str:
        if self.api_base_url is None:
            raise ValueError("API base URL is not set.")
        return self.api_base_url.rstrip("/")

    @functools.cached_property
    def health_endpoint(self) -> str:
        return f"{self._base_url}/health"

    @functools.cached_property
    def detect_endpoint(self) -> str:
        return f"{self._base_url}/detect"

    @functools.cached_property
    def detect_upload_endpoint(self) -> str:
        return f"{self._base_url}/detect/upload"

    @functools.cached_property
    def update_class_endpoint(self) -> str:
        return f"{self._base_url}/detect/update_class"


class Config(BaseModel):
    screen: PluginConfig


plugin_config = get_plugin_config(Config).screen
