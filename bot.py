import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OB11Adapter
from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.log import logger

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

nonebot.init()
app = nonebot.get_asgi()
driver = nonebot.get_driver()
driver.register_adapter(OB11Adapter)
driver.register_adapter(QQAdapter)
nonebot.load_from_toml("pyproject.toml")


if __name__ == "__main__":
    nonebot.run()
