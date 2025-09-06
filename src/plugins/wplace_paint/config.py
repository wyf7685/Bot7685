from pathlib import Path
from typing import Any

from nonebot import get_plugin_config
from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import BaseModel, Field

from src.utils import ConfigFile, ConfigListFile

DATA_DIR = get_plugin_data_dir()
TEMPLATE_DIR = Path(__file__).parent / "templates"


class UserConfig(BaseModel):
    token: str
    cf_clearance: str
    target_data: dict[str, Any]
    user_id: str
    notify_mins: int = 10
    wp_user_id: int | None = None
    wp_user_name: str | None = None
    max_overflow_notify: int = 3
    target_droplets: int | None = None
    bind_groups: set[str] = Field(default_factory=set)
    adapter: str | None = None

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)

    def save(self) -> None:
        cfgs = users.load()
        for cfg in cfgs[:]:
            if cfg is self or (
                cfg.user_id == self.user_id
                and cfg.wp_user_id is not None
                and cfg.wp_user_id == self.wp_user_id
            ):
                cfgs.remove(cfg)
                break
        cfgs.append(self)
        users.save(cfgs)


users = ConfigListFile(DATA_DIR / "users.json", UserConfig)

RankConfig = dict[str, set[int]]  # group target id -> set of region id
ranks = ConfigFile[RankConfig](DATA_DIR / "rank.json", RankConfig, dict)


class _ProxyConfig(BaseModel):
    proxy: str | None = None


proxy = get_plugin_config(_ProxyConfig).proxy
