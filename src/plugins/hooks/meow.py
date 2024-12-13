from typing import Any

from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment


@BaseBot.on_calling_api
async def _(bot: BaseBot, api: str, data: dict[str, Any]) -> None:
    if not isinstance(bot, Bot):
        return

    if api not in {"send_msg", "send_group_msg", "send_private_msg"}:
        return

    if "message" not in data:
        return

    message = data["message"]

    if (
        isinstance(message, Message)
        and message
        and isinstance(seg := message[-1], MessageSegment)
        and seg.type == "text"
    ):
        seg.data["text"] += "喵"
    elif (
        isinstance(message, list)
        and message
        and isinstance(seg := message[-1], dict)
        and seg.get("type") == "text"
    ):
        seg["data"]["text"] += "喵"
