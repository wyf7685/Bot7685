from collections.abc import Callable

from nonebot import get_driver
from nonebot.plugin import get_loaded_plugins


def make_disposer(dispose: object) -> Callable[[], object]:
    return (lambda: None) if dispose is None or not callable(dispose) else dispose


@get_driver().on_startup
async def _() -> None:
    for plugin in get_loaded_plugins():
        if plugin.module_name.startswith("src.plugins."):
            plugin.module.dispose = make_disposer(  # pyright:ignore[reportAttributeAccessIssue]
                getattr(plugin.module, "dispose", None)
            )
