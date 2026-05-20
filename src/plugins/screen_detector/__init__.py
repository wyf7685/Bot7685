from nonebot import logger, require

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
require("src.service.cache")
from .config import plugin_config

if plugin_config.api_base_url:
    logger.debug(
        f"Screen Detector plugin loaded with API base URL: {plugin_config.api_base_url}"
    )
    from . import detect as detect
    from . import reaction as reaction
else:
    logger.warning(
        "Screen Detector plugin loaded without API base URL. "
        "Detection will be disabled."
    )
