from collections.abc import Mapping

from nonebot.adapters import Bot as BaseBot
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot_plugin_alconna import Reference, UniMessage

from ..contracts import ForwardFetchError, ForwardUnsupportedError


def _message_from_array(content: object) -> Message:
    if isinstance(content, Message):
        return content.copy()
    if isinstance(content, str):
        raise ForwardUnsupportedError(
            "OneBot V11 CQ-code forwarded content is unsupported"
        )
    if not isinstance(content, list):
        raise ForwardUnsupportedError(
            "OneBot V11 forwarded node content is not a message array"
        )

    segments: list[MessageSegment] = []
    for item in content:
        if not isinstance(item, Mapping):
            raise ForwardUnsupportedError(
                "OneBot V11 forwarded node contains an invalid segment"
            )
        segment_type = item.get("type")
        data = item.get("data")
        if not isinstance(segment_type, str) or not isinstance(data, Mapping):
            raise ForwardUnsupportedError(
                "OneBot V11 forwarded node contains an invalid segment"
            )
        segments.append(MessageSegment(segment_type, dict(data)))
    return Message(segments)


def _node_content(node: object) -> object:
    if not isinstance(node, Mapping):
        raise ForwardUnsupportedError("OneBot V11 returned an invalid forwarded node")
    if node.get("type") == "node":
        data = node.get("data")
        if not isinstance(data, Mapping) or "content" not in data:
            raise ForwardUnsupportedError(
                "OneBot V11 returned a reference-only forwarded node"
            )
        return data["content"]
    if "message" in node:
        return node["message"]
    if "content" in node:
        return node["content"]
    raise ForwardUnsupportedError(
        "OneBot V11 returned an unsupported forwarded node shape"
    )


async def resolve(
    bot: BaseBot,
    event: Event,
    reference: Reference,
) -> tuple[UniMessage, ...]:
    del event
    if not isinstance(bot, Bot):
        raise ForwardUnsupportedError("OneBot V11 adapter bot type is unavailable")
    if (
        reference.children
        or not reference.id
        or not (reference_id := reference.id.strip())
    ):
        raise ForwardUnsupportedError(
            "OneBot V11 forwarded-message reference is invalid"
        )

    result = await bot.get_forward_msg(id=reference_id)
    nodes = result.get("message")
    if nodes is None:
        nodes = result.get("messages")
    if not isinstance(nodes, list):
        raise ForwardUnsupportedError(
            "OneBot V11 returned an unsupported forwarded-message response"
        )
    if not nodes:
        raise ForwardFetchError("OneBot V11 returned an empty forwarded message")

    messages: list[UniMessage] = []
    for node in nodes:
        native = _message_from_array(_node_content(node))
        if native:
            messages.append(UniMessage.of(native, bot=bot))
    if not messages:
        raise ForwardFetchError("OneBot V11 returned no usable forwarded nodes")
    return tuple(messages)


__all__ = ["resolve"]
