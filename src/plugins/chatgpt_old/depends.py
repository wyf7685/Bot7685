from typing import Annotated

from nonebot.adapters.onebot.v11 import (
    GROUP_ADMIN,
    GROUP_OWNER,
    Bot,
    GroupMessageEvent,
    MessageEvent,
    PrivateMessageEvent,
)
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot.permission import SUPERUSER, Permission
from nonebot.rule import Rule
from nonebot_plugin_alconna import AlcMatches, At, UniMsg

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
    async def msg_at(message: UniMsg) -> str:
        if message.has(At):
            return message[At, 0].target
        Matcher.skip()

    return Depends(msg_at)


def _AtTarget():
    async def at_target(result: AlcMatches) -> str:
        if target := result.query[At]("target"):
            return target.target
        Matcher.skip()

    return Depends(at_target)


IS_ADMIN = Rule(admin_check)
AuthCheck = Depends(auth_check)
AdminCheck = Annotated[bool, Depends(admin_check)]
ALLOW_PRIVATE = Permission(allow_private)
GroupId = Annotated[str, _GroupId()]
MsgAt = Annotated[str, _MsgAt()]
AtTarget = Annotated[str, _AtTarget()]
