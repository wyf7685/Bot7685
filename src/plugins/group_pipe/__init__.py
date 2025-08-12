from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
require("src.plugins.cache")
require("src.plugins.gtg")
require("src.plugins.upload_cos")

from . import (  # pyright: ignore[reportUnusedImport]  # noqa: F401
    adapters,
    hooks,
    matchers,
)

__plugin_meta__ = PluginMetadata(
    name="group_pipe",
    description="群组管道",
    usage="pipe --help",
    type="application",
    supported_adapters={
        "~onebot.v11",
        "~telegram",
        "~discord",
    },
)

from .adapter import get_converter as get_converter
from .adapter import get_sender as get_sender

__all__ = ["get_converter", "get_sender"]
