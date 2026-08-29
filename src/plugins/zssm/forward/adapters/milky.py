from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event
from nonebot.adapters.milky import Bot
from nonebot_plugin_alconna import Reference, UniMessage

from ..contracts import ForwardFetchError, ForwardUnsupportedError


async def resolve(
    bot: BaseBot,
    event: Event,
    reference: Reference,
) -> tuple[UniMessage, ...]:
    del event
    if not isinstance(bot, Bot):
        raise ForwardUnsupportedError("Milky adapter bot type is unavailable")
    if (
        reference.children
        or not reference.id
        or not (reference_id := reference.id.strip())
    ):
        raise ForwardUnsupportedError("Milky forwarded-message reference is invalid")

    forwarded = await bot.get_forwarded_messages(forward_id=reference_id)
    if not forwarded:
        raise ForwardFetchError("Milky returned an empty forwarded message")
    try:
        return tuple(UniMessage.of(item.message, bot=bot) for item in forwarded)
    except Exception as error:
        raise ForwardUnsupportedError(
            "Milky returned unsupported forwarded content"
        ) from error


__all__ = ["resolve"]
