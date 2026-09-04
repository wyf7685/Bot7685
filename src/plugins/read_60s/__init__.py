from nonebot.plugin import PluginMetadata, inherit_supported_adapters

__plugin_meta__ = PluginMetadata(
    name="read_60s",
    description="每日60S读世界",
    usage="每日60S读世界",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
)

from . import matcher as matcher
from . import scheduler as scheduler
