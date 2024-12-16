from pathlib import Path

from nonebot.plugin import PluginMetadata, load_plugins

__plugin_meta__ = PluginMetadata(
    name="hooks",
    description="set bot hooks",
    usage="None",
    type="application",
)


load_plugins(Path(__file__).parent.resolve().as_posix())
