from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Command

Command("about").alias("关于").action(
    lambda: "https://github.com/wyf7685/Bot7685"
).build()
