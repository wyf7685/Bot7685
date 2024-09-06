import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.log import logger

# from nonebot.adapters.qq import Adapter as QQAdapter
# from nonebot.adapters.telegram import Adapter as TelegramAdapter

logger.add(
    "./logs/{time:YYYY-MM-DD}.log",
    rotation="00:00",
    level="DEBUG",
    diagnose=True,
    format=(
        "<g>{time:HH:mm:ss}</g> "
        "[<lvl>{level}</lvl>] "
        "<c><u>{name}</u></c> | "
        "<c>{function}:{line}</c>| "
        "{message}"
    ),
)


def custom_load():
    import pathlib
    import tomllib

    with open("pyproject.toml", encoding="utf-8") as f:
        data = tomllib.loads(f.read())
    nonebot_data = data.get("tool", {}).get("nonebot")
    plugins: list[str] = nonebot_data.get("plugins", [])

    for p in pathlib.Path("src/dev").iterdir():
        if (p.is_dir() and (name := p.name) in plugins) or (
            p.is_file() and p.suffix == ".py" and (name := p.stem) in plugins
        ):
            plugins.remove(name)
            logger.opt(colors=True).warning(
                f'优先加载来自 "<m>src.dev.{name}</m>" 的插件 "<y>{name}</y>"'
            )

    nonebot.load_all_plugins(plugins, ["src/plugins", "src/dev"])


nonebot.init()
app = nonebot.get_asgi()
driver = nonebot.get_driver()
driver.register_adapter(OB11Adapter)
# driver.register_adapter(QQAdapter)
# driver.register_adapter(TelegramAdapter)
# nonebot.load_from_toml("pyproject.toml")
custom_load()


if __name__ == "__main__":
    nonebot.run()
