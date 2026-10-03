from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import Image, Reply, UniMessage


async def fetch_image(bot: Bot, image: Image) -> bytes | None:
    if bot.adapter.get_name() != "Milky":
        return None
    from .milky import fetch_image as fetch_milky_image

    return await fetch_milky_image(bot, image)


def _quoted_message_from_event(
    bot: Bot,
    event: Event,
    reply: Reply,
) -> UniMessage | None:
    if bot.adapter.get_name() != "Discord":
        return None
    from .discord import quoted_message_from_event

    return quoted_message_from_event(bot, event, reply)


def _normalize_input_message(bot: Bot, message: UniMessage) -> UniMessage:
    if bot.adapter.get_name() != "Discord":
        return message
    from .discord import normalize_message

    return normalize_message(message)


__all__ = ["fetch_image"]
