from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.milky import Bot
from nonebot.internal.driver.model import Request
from nonebot_plugin_alconna import Image


async def fetch_image(bot: BaseBot, image: Image) -> bytes | None:
    if not isinstance(bot, Bot):
        return None
    if image.raw or image.path or image.url or not image.id:
        return None

    url = await bot.get_resource_temp_url(resource_id=image.id)
    response = await bot.adapter.request(Request("GET", url))
    content = response.content
    if isinstance(content, str):
        raise TypeError("Milky image resource must contain bytes")
    return content


__all__ = ["fetch_image"]
