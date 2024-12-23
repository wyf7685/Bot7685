import nonebot

from src.bootstrap import load_config, load_plugins

nonebot.init(**load_config())
app = nonebot.get_asgi()
load_plugins()


if __name__ == "__main__":
    nonebot.run()
