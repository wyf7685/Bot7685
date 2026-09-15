from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot_plugin_uninfo import Session, get_session

from .config import resolve_state
from .registry import SELF_PLUGIN_NAMES, resolve_matcher_plugin
from .session import current_target


@run_preprocessor
async def plugin_switch_guard(matcher: Matcher, bot: Bot, event: Event) -> None:
    try:
        session: Session | None = await get_session(bot, event)
    except Exception:
        return
    if session is None:
        return

    plugin_name = resolve_matcher_plugin(matcher)
    if plugin_name is None or plugin_name in SELF_PLUGIN_NAMES:
        return

    target = current_target(session)
    state = resolve_state(
        plugin_name,
        target.adapter,
        group_id=target.group_id,
        user_id=target.user_id,
    )
    if state == "disabled":
        raise IgnoredException(f"plugin {plugin_name!r} is disabled")
