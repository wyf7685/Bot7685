from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="Plugin Manager",
    description="Plugin-level runtime switch manager.",
    usage=(
        "/plugin list | /plugin status <plugin> | "
        "/plugin enable <plugin> | /plugin disable <plugin>"
    ),
    type="application",
    extra={"author": "FrostN0v0"},
)

from . import commands as commands
from . import guard as guard
