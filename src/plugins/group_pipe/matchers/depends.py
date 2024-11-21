from typing import Annotated

from nonebot.adapters import Bot, Event
from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot_plugin_alconna import Target, UniMessage


async def _target(bot: Bot, event: Event) -> Target:
    try:
        return UniMessage.get_target(event, bot)
    except Exception:
        Matcher.skip()


MsgTarget = Annotated[Target, Depends(_target, use_cache=True)]
