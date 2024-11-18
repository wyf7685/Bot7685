import importlib
import logging
import pathlib
import tomllib

import nonebot

logging.getLogger("httpx").setLevel(logging.WARNING)
nonebot.logger.add(
    "./logs/{time:YYYY-MM-DD}.log",
    rotation="00:00",
    level="DEBUG",
    format=(
        "<g>{time:HH:mm:ss}</g> "
        "[<lvl>{level}</lvl>] "
        "<c><u>{name}</u></c> | "
        "<c>{function}:{line}</c> | "
        "{message}"
    ),
)
nonebot.logger.add(
    "./logs/{time:YYYY-MM-DD}.colorize.log",
    rotation="00:00",
    level="DEBUG",
    colorize=True,
    diagnose=True,
    format=(
        "<g>{time:HH:mm:ss}</g> "
        "[<lvl>{level}</lvl>] "
        "<c><u>{name}</u></c> | "
        "<c>{function}:{line}</c> | "
        "{message}"
    ),
)


def custom_load() -> None:
    nonebot_data: dict = (
        tomllib.loads(pathlib.Path("pyproject.toml").read_text("utf-8"))
        .get("tool", {})
        .get("nonebot")
    )

    for item in nonebot_data.get("adapters", []):
        module = importlib.import_module(item["module_name"])
        nonebot.get_driver().register_adapter(module.Adapter)

    plugins: list[str] = nonebot_data.get("plugins", [])
    for p in pathlib.Path("src/dev").iterdir():
        if (p.is_dir() and (name := p.name) in plugins) or (
            p.is_file() and p.suffix == ".py" and (name := p.stem) in plugins
        ):
            plugins.remove(name)
            nonebot.logger.opt(colors=True).warning(
                f'优先加载来自 "<m>src.dev.{name}</m>" 的插件 "<y>{name}</y>"'
            )

    nonebot.load_all_plugins(plugins, ["src/plugins", "src/dev"])


nonebot.init()
app = nonebot.get_asgi()
custom_load()


if __name__ == "__main__":
    nonebot.run()
