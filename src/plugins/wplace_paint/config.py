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
    wp_user_id: int | None = None
    wp_user_name: str | None = None
    max_overflow_notify: int = 3
    target_droplets: int | None = None

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)

    def save(self) -> None:
        cfgs = config.load()
        for cfg in cfgs[:]:
            if cfg is self or (
                cfg.user_id == self.user_id
                and cfg.wp_user_id is not None
                and cfg.wp_user_id == self.wp_user_id
            ):
                cfgs.remove(cfg)
                break
        cfgs.append(self)
        config.save(cfgs)


config = ConfigListFile(get_plugin_data_file("config.json"), ConfigModel)
