from typing import TYPE_CHECKING, Annotated

from nonebot.matcher import Matcher
from nonebot.params import Depends
from nonebot_plugin_alconna import Target, get_target

if TYPE_CHECKING:
    from nonebot.adapters import Bot, Event
    from nonebot.typing import T_State

_STATE_KEY_TARGET = "STATE_KEY_TARGET"


async def _target(bot: Bot, event: Event, state: T_State) -> Target:
    if _STATE_KEY_TARGET in state:
        return state[_STATE_KEY_TARGET]

    try:
        target = get_target(event, bot)
    except Exception:
        Matcher.skip()
    else:
        state[_STATE_KEY_TARGET] = target
        return target


MsgTarget = Annotated[Target, Depends(_target, use_cache=True)]
