import importlib

from nonebot import get_adapters
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="friend_add",
    description="好友申请处理",
    usage="自动处理好友申请",
    type="application",
    supported_adapters={"~onebot.v11", "~milky"},
)

_ADAPTERS = {
    "Milky": "milky",
    "OneBot V11": "ob11",
}


for adapter in get_adapters():
    if module := _ADAPTERS.get(adapter):
        importlib.import_module(f"{__package__}.{module}")
