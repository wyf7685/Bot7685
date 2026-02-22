from pathlib import Path

from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir
from PIL import Image
from pydantic import BaseModel

from src.utils import ConfigFile

from .utils import WplacePixelCoords

DATA_DIR = get_plugin_data_dir()
IMAGE_DIR = DATA_DIR / "images"
IMAGE_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR = Path(__file__).parent / "templates"


# scene id -> set of region id
ranks = ConfigFile(DATA_DIR / "rank.json", dict[int, set[int]], dict)


class TemplateConfig(BaseModel):
    scene_id: int
    coords: WplacePixelCoords

    @property
    def file(self) -> Path:
        return IMAGE_DIR / f"{self.scene_id}.png"

    def load(self) -> tuple[Image.Image, tuple[WplacePixelCoords, WplacePixelCoords]]:
        im = Image.open(self.file)
        w, h = im.size
        return im, (self.coords, self.coords.offset(w - 1, h - 1))


# scene id -> TemplateConfig
templates = ConfigFile(DATA_DIR / "templates.json", dict[int, TemplateConfig], dict)


class _ProxyConfig(BaseModel):
    proxy: str | None = None


proxy = get_plugin_config(_ProxyConfig).proxy
