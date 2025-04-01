from nonebot import require

require("nonebot_plugin_htmlrender")
from nonebot_plugin_htmlrender import browser


async def _() -> None: ...


browser.init_browser = _
