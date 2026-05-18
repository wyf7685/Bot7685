from nonebot import get_plugin_config
from pydantic import BaseModel


class PluginConfig(BaseModel):
    api_base_url: str | None = None

    @property
    def health_endpoint(self) -> str:
        if self.api_base_url is None:
            raise ValueError("API base URL is not set.")
        return f"{self.api_base_url}/health"

    @property
    def detect_endpoint(self) -> str:
        if self.api_base_url is None:
            raise ValueError("API base URL is not set.")
        return f"{self.api_base_url}/detect"

    @property
    def detect_upload_endpoint(self) -> str:
        if self.api_base_url is None:
            raise ValueError("API base URL is not set.")
        return f"{self.api_base_url}/detect/upload"


class Config(BaseModel):
    screen: PluginConfig


plugin_config = get_plugin_config(Config).screen
