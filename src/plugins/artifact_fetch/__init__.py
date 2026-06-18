from nonebot.plugin import PluginMetadata

from . import matchers as matchers
from .config import Config

__plugin_meta__ = PluginMetadata(
    name="Artifact Fetch",
    description="A plugin to fetch GitHub Actions artifacts.",
    usage="<TODO>",
    type="application",
    config=Config,
    supported_adapters={"~milky"},
)
