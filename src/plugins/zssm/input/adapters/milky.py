from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.milky import Bot
from nonebot.internal.driver.model import Request
from nonebot_plugin_alconna import Image, Other, Text, UniMessage


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


def normalize_message(message: UniMessage) -> UniMessage:
    if not any(
        isinstance(segment, Other) and segment.origin.type == "markdown"
        for segment in message
    ):
        return message

    normalized = UniMessage()
    for segment in message:
        if isinstance(segment, Other) and segment.origin.type == "markdown":
            content = segment.origin.data.get("content")
            if isinstance(content, str):
                normalized.append(Text(content))
                continue
        normalized.append(segment)
    return normalized


__all__ = ["fetch_image", "normalize_message"]
