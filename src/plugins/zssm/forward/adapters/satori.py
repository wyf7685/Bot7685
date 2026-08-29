from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event
from nonebot.adapters.satori import Bot, Message
from nonebot.adapters.satori.element import parse
from nonebot.adapters.satori.event import MessageEvent
from nonebot.adapters.satori.message import Author
from nonebot_plugin_alconna import Other, Reference, Segment, UniMessage

from ..contracts import ForwardFetchError, ForwardUnsupportedError


def _inline_message(reference: Reference) -> UniMessage:
    segments: list[Segment] = []
    for child in reference.children:
        if not isinstance(child, Segment):
            raise ForwardUnsupportedError(
                "Satori forwarded message contains an unsupported node"
            )
        if isinstance(child, Other) and isinstance(child.origin, Author):
            continue
        segments.append(child)
    if not segments:
        raise ForwardFetchError("Satori inline forwarded message is empty")
    return UniMessage(segments).copy()


async def resolve(
    bot: BaseBot,
    event: Event,
    reference: Reference,
) -> tuple[UniMessage, ...]:
    if not isinstance(bot, Bot):
        raise ForwardUnsupportedError("Satori adapter bot type is unavailable")
    if reference.children:
        return (_inline_message(reference),)
    if not reference.id or not (reference_id := reference.id.strip()):
        raise ForwardUnsupportedError("Satori forwarded-message reference is invalid")
    if not isinstance(event, MessageEvent):
        raise ForwardUnsupportedError("Satori message channel context is unavailable")

    forwarded = await bot.message_get(
        channel_id=event.channel.id,
        message_id=reference_id,
    )
    if not forwarded.content:
        raise ForwardFetchError("Satori returned an empty forwarded message")
    try:
        native = Message.from_satori_element(parse(forwarded.content))
        message = UniMessage.of(native, bot=bot)
    except Exception as error:
        raise ForwardUnsupportedError(
            "Satori returned unsupported forwarded content"
        ) from error
    if not message:
        raise ForwardFetchError("Satori returned no usable forwarded content")
    return (message,)


__all__ = ["resolve"]
