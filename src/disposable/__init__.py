from . import bot, driver, event, matcher, plugin
from .plugin import dispose_all as dispose_all
from .plugin import dispose_plugin as dispose_plugin
from .plugin import external_dispose as external_dispose


def setup_disposable() -> None:
    bot.setup_disposable()
    driver.setup_disposable()
    event.setup_disposable()
    matcher.setup_disposable()
    plugin.setup_disposable()
