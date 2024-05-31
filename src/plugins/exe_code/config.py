from typing import Set

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class Config(BaseModel):
    user: Set[str] = Field(default_factory=set, alias="exe_code_user")
    group: Set[str] = Field(default_factory=set, alias="exe_code_group")


cfg = get_plugin_config(Config)
