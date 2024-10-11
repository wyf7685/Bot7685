import contextlib
from typing import TYPE_CHECKING

from nonebot import get_plugin_config, on_keyword, on_message, require
from nonebot.adapters import Bot, Event
from nonebot.exception import ActionFailed
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")
from nonebot_plugin_alconna import MsgTarget
from nonebot_plugin_session import EventSession

if TYPE_CHECKING:
    from nonebot_plugin_exe_code.interface import get_api_class
else:
    require("src.dev.nonebot_plugin_exe_code")
    from src.dev.nonebot_plugin_exe_code.interface import get_api_class

class Config(BaseModel):
    reaction_users: set[str] = set()


config = get_plugin_config(Config)


def _rule_bubble(target: MsgTarget) -> bool:
    return not target.private


bubble = on_keyword({"冒泡"}, _rule_bubble)


@bubble.handle()
async def handle_bubble(bot: Bot, event: Event, session: EventSession) -> None:
    api = get_api_class(bot)(bot, event, session, {})
    if set_reaction := getattr(api, "set_reaction", None):
        with contextlib.suppress(ActionFailed):
            await set_reaction(38, api.mid)


def _rule(event: Event, target: MsgTarget) -> bool:
    return not target.private and event.get_user_id() in config.reaction_users


matcher = on_message(rule=_rule, block=False)


@matcher.handle()
async def _(bot: Bot, event: Event, session: EventSession) -> None:
    api = get_api_class(bot)(bot, event, session, {})
    if set_reaction := getattr(api, "set_reaction", None):
        with contextlib.suppress(ActionFailed):
            await set_reaction(424, api.mid)
            await set_reaction(38, api.mid)
