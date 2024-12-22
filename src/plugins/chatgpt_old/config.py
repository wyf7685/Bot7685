# ruff: noqa

from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel

from .apikey import APIKeyPool


class PluginConfig(BaseModel):
    api_key: str | list[str]
    key_load_balancing: bool = False
    history_save_path: Path = Path("data/chatgpt/chat_history").resolve()
    preset_path: Path = Path("data/chatgpt/presets").resolve()
    openai_proxy: str | None = None
    openai_api_base: str = "https://api.openai.com/v1"
    chat_memory_max: int = 10
    history_max: int = 100
    temperature: float = 0.5
    gpt_model_name: str = "gpt-3.5-turbo"
    allow_private: bool = True
    change_chat_to: str | None = None
    max_tokens: int = 1024
    auto_create_preset_info: bool = True
    customize_prefix: str = "/"
    customize_talk_cmd: str = "talk"
    timeout: int = 10
    default_only_admin: bool = False
    at_sender: bool = True

    @property
    def api_key_pool(self):
        return APIKeyPool(self.api_key)


class Config(BaseModel):
    chatgpt: PluginConfig


plugin_config = get_plugin_config(Config).chatgpt
