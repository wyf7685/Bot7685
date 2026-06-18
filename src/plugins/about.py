from nonebot_plugin_alconna import Command

matcher = (
    Command("about")
    .alias("关于")
    .action(lambda: "https://github.com/wyf7685/Bot7685")
    .build()
)
