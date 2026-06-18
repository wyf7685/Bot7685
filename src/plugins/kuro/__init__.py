from nonebot.plugin import PluginMetadata, inherit_supported_adapters

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="kuro",
    description="库洛插件",
    usage="None",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
        "nonebot_plugin_waiter",
    ),
    config=Config,
)

from . import matchers as matchers
from . import schedulers as schedulers
