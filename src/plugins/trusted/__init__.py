from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="trusted",
    description="Manage trusted user or group",
    usage="trust -h",
    type="library",
)

from . import matcher as matcher
from .trust_data import TrustedUser as TrustedUser

__all__ = ["TrustedUser"]
