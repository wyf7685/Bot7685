from nonebot import get_driver
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="on_driver_startup",
    description="Start jobs on driver startup",
    usage="None",
    type="application",
    supported_adapters=None,
)


@get_driver().on_startup
def clean_pycache() -> None:
    from pathlib import Path
    from queue import Queue
    from shutil import rmtree

    que = Queue[Path]()
    (put := que.put)(Path.cwd())
    while not que.empty():
        for p in filter(Path.is_dir, que.get().iterdir()):
            (rmtree if p.name == "__pycache__" else put)(p)
