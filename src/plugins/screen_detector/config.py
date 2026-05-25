from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class PluginConfig(BaseModel):
    enabled_scenes: set[str] = Field(default_factory=set)
    api_base_url: str | None = Field(default=None)


class Config(BaseModel):
    screen: PluginConfig


plugin_config = get_plugin_config(Config).screen
