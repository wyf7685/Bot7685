from typing import Annotated

from nonebot.adapters.onebot.v11 import (
    GROUP_ADMIN,
    GROUP_OWNER,
    Bot,
    GroupMessageEvent,
    Message,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from nonebot.params import EventMessage, Depends
from nonebot.permission import SUPERUSER, Permission
from nonebot.rule import Rule

from .config import plugin_config
from .session import get_group_id, session_container


async def admin_check(bot: Bot, event: MessageEvent) -> bool:
    return not isinstance(event, GroupMessageEvent) or (
        (await SUPERUSER(bot, event))
        or (await GROUP_ADMIN(bot, event))
        or (await GROUP_OWNER(bot, event))
    )


async def auth_check(matcher: Matcher, bot: Bot, event: MessageEvent) -> None:
    if isinstance(event, PrivateMessageEvent):
        return
    group_id = get_group_id(event)
    if session_container.get_group_auth(group_id) and not (
        await admin_check(bot, event)
    ):
        matcher.skip()


async def allow_private(event: MessageEvent) -> bool:
    return isinstance(event, GroupMessageEvent) or plugin_config.allow_private


def _GroupId():
    async def group_id(event: MessageEvent) -> str:
        return get_group_id(event)

    return Depends(group_id)


def _MsgAt():
    async def msg_at(matcher: Matcher, message: Message = EventMessage()) -> int:
        for seg in message.include("at"):
            qq: str = seg.data.get("qq", "all")
            if qq.isdigit():
                return int(qq)
        matcher.skip()

    return Depends(msg_at)


IS_ADMIN = Rule(admin_check)
AuthCheck = Depends(auth_check)
AdminCheck = Annotated[bool, Depends(admin_check)]
ALLOW_PRIVATE = Permission(allow_private)
GroupId = Annotated[str, _GroupId()]
MsgAt = Annotated[int, _MsgAt()]
