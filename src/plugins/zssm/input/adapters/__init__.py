from nonebot.adapters import Bot
from nonebot_plugin_alconna import Image


async def fetch_image(bot: Bot, image: Image) -> bytes | None:
    if bot.adapter.get_name() != "Milky":
        return None
    from .milky import fetch_image as fetch_milky_image

    return await fetch_milky_image(bot, image)


__all__ = ["fetch_image"]
