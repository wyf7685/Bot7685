from nonebot.plugin import get_plugin_config
from pydantic import BaseModel


class Config(BaseModel):
    patch_event_debug: bool = False


plugin_config = get_plugin_config(Config)
