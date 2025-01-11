from nonebot import get_plugin_config
from pydantic import BaseModel


class AutoSignin(BaseModel):
    hour: int
    minute: int


class PluginConfig(BaseModel):
    auto_signin: AutoSignin


class Config(BaseModel):
    kuro: PluginConfig


config = get_plugin_config(Config).kuro
