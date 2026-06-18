from nonebot import logger, require

from .config import plugin_config

if plugin_config.api_base_url:
    logger.debug(
        f"Screen Detector plugin loaded with API base URL: {plugin_config.api_base_url}"
    )
    require("nonebot_plugin_alconna")
    require("nonebot_plugin_apscheduler")
    require("nonebot_plugin_uninfo")
    require("src.plugins.upload_cos")
    require("src.service.cache")
    require("src.service.task")
    from . import command as command
    from . import detect as detect
    from . import reaction as reaction
    from . import scheduler as scheduler
else:
    logger.warning(
        "Screen Detector plugin loaded without API base URL. "
        "Detection will be disabled."
    )
