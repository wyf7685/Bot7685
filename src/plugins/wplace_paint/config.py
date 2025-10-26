from pathlib import Path
from typing import Any

from nonebot import get_plugin_config
from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_data_dir
from PIL import Image
from pydantic import BaseModel, Field

from src.utils import ConfigFile, ConfigListFile

from .schemas import PurchaseItem
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
    auto_purchase: PurchaseItem | None = None

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
                for attr in set(type(self).model_fields) - {
                    "token",
                    "cf_clearance",
                    "user_id",
                    "wp_user_id",
                    "wp_user_name",
                }:
                    setattr(self, attr, getattr(cfg, attr))

        cfgs.append(self)
        users.save(cfgs)


users = ConfigListFile(DATA_DIR / "users.json", UserConfig)

# group target id -> set of region id
ranks = ConfigFile(DATA_DIR / "rank.json", dict[str, set[int]], dict)


class TemplateConfig(BaseModel):
    key: str
    coords: WplacePixelCoords

    @property
    def file(self) -> Path:
        return IMAGE_DIR / f"{self.key}.png"

    def load(self) -> tuple[Image.Image, tuple[WplacePixelCoords, WplacePixelCoords]]:
        im = Image.open(self.file)
        w, h = im.size
        return im, (self.coords, self.coords.offset(w - 1, h - 1))


# group target hash -> TemplateConfig
templates = ConfigFile(DATA_DIR / "templates.json", dict[str, TemplateConfig], dict)


class _ProxyConfig(BaseModel):
    proxy: str | None = None


proxy = get_plugin_config(_ProxyConfig).proxy
