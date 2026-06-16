from typing import Any

from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel, Field

from src.utils import ConfigFile


class PluginConfig(BaseModel):
    enabled_scenes: set[str] = Field(default_factory=set)
    api_base_url: str | None = Field(default=None)


class Config(BaseModel):
    screen: PluginConfig


plugin_config = get_plugin_config(Config).screen


pkg_subs = ConfigFile(
    get_plugin_data_file("package-subs.json"), list[dict[str, Any]], list
)
