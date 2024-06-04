import nonebot
# from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11Adapter
from nonebot.adapters.qq import Adapter as QQAdapter
from nonebot.log import default_filter, default_format, logger

logger.add(
    "./logs/{time:YYYY-MM-DD}.log",
    rotation="00:00",
    level=0,
    diagnose=False,
    filter=default_filter,
    format=default_format,
)

nonebot.init()

driver = nonebot.get_driver()
# driver.register_adapter(ONEBOT_V11Adapter)
driver.register_adapter(QQAdapter)


nonebot.load_from_toml("pyproject.toml")

if __name__ == "__main__":
    nonebot.run()
