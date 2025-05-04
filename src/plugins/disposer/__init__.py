from nonebot.plugin import PluginMetadata

from . import apscheduler as apscheduler
from . import bot7685 as bot7685

__plugin_meta__ = PluginMetadata(
    name="Disposer",
    description="register disposer for third-party plugins",
    usage="None",
    type="library",
)
