from typing import Any

from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_data_file
from pydantic import BaseModel

from src.utils import ConfigListFile


class ConfigModel(BaseModel):
    token: str
    cf_clearance: str
    target_data: dict[str, Any]
    user_id: str
    notify_mins: int = 10

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)


config = ConfigListFile(get_plugin_data_file("config.json"), ConfigModel)
