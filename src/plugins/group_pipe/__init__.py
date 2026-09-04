from nonebot.plugin import PluginMetadata

from . import adapters as adapters
from . import hooks as hooks
from . import matchers as matchers

__plugin_meta__ = PluginMetadata(
    name="group_pipe",
    description="群组管道",
    usage="pipe --help",
    type="application",
    supported_adapters={
        "~onebot.v11",
        "~telegram",
        "~discord",
        "~milky",
    },
)

from .adapter import get_converter as get_converter
from .adapter import get_sender as get_sender

__all__ = ["get_converter", "get_sender"]
