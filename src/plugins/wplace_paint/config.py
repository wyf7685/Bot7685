from pathlib import Path
from typing import Any

from nonebot import get_plugin_config
from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import BaseModel, Field

from src.utils import ConfigFile, ConfigListFile

from .utils import WplacePixelCoords

DATA_DIR = get_plugin_data_dir()
IMAGE_DIR = DATA_DIR / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR = Path(__file__).parent / "templates"


class UserConfig(BaseModel):
    token: str
    cf_clearance: str
    target_data: dict[str, Any]
    user_id: str
    notify_mins: int = 10
    wp_user_id: int = 0
    wp_user_name: str = ""
    max_overflow_notify: int = 3
    target_droplets: int | None = None
    bind_groups: set[str] = Field(default_factory=set)
    adapter: str | None = None
    auto_paint_target_hash: str | None = None

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)

    def save(self) -> None:
        cfgs = users.load()
        for cfg in cfgs[:]:
            if cfg is self:
                cfgs.remove(cfg)
            elif cfg.user_id == self.user_id and cfg.wp_user_id == self.wp_user_id:
                cfgs.remove(cfg)
                for attr in (
                    "target_data",
                    "notify_mins",
                    "max_overflow_notify",
                    "target_droplets",
                    "bind_groups",
                ):
                    setattr(self, attr, getattr(cfg, attr))

        cfgs.append(self)
        users.save(cfgs)


users = ConfigListFile(DATA_DIR / "users.json", UserConfig)

RankConfig = dict[str, set[int]]  # group target id -> set of region id
ranks = ConfigFile[RankConfig](DATA_DIR / "rank.json", RankConfig, dict)


class TemplateConfig(BaseModel):
    coords: WplacePixelCoords
    image: str  # image file in IMAGE_DIR

    @property
    def file(self) -> Path:
        return IMAGE_DIR / self.image


# group target id -> TemplateConfig
templates = ConfigFile(DATA_DIR / "templates.json", dict[str, TemplateConfig], dict)


class _ProxyConfig(BaseModel):
    proxy: str | None = None


proxy = get_plugin_config(_ProxyConfig).proxy
