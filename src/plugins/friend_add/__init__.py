from nonebot import get_adapters, load_plugin
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="friend_add",
    description="好友申请处理",
    usage="自动处理好友申请",
    type="application",
    supported_adapters={"~onebot.v11", "~milky"},
)

ADAPTER_PLUGINS = {
    "Milky": "milky",
    "OneBot V11": "ob11",
}

for adapter in get_adapters():
    if (module_name := ADAPTER_PLUGINS.get(adapter)) and load_plugin(
        f"{__package__}.{module_name}"
    ) is None:
        raise RuntimeError(f"Failed to load the {adapter} friend-add plugin")
