import atexit
import contextlib
from pathlib import Path

from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="clean_shortcut",
    description="Clean shortcut.* on program exit",
    usage="None",
    type="application",
    supported_adapters=None,
)


@atexit.register
def clean_shortcut() -> None:
    for path in Path.cwd().glob("shortcut.*"):
        with contextlib.suppress(Exception):
            path.unlink()
