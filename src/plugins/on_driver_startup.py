from nonebot import get_driver


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
