import contextlib
from typing import TYPE_CHECKING, cast

import anyio
from nonebot import get_plugin_config, on_message, require
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")
from nonebot_plugin_alconna import MsgTarget
from nonebot_plugin_session import EventSession

if TYPE_CHECKING:
    from nonebot_plugin_exe_code.interface import get_api_class
    from nonebot_plugin_exe_code.interface.adapters.onebot11 import API as V11API
else:
    try:
        require("src.dev.nonebot_plugin_exe_code")
        from src.dev.nonebot_plugin_exe_code.interface import get_api_class
    except Exception:
        require("nonebot_plugin_exe_code")
        from nonebot_plugin_exe_code.interface import get_api_class

from .bubble_check import check_bubble_word

__plugin_meta__ = PluginMetadata(
    name="reaction",
    description="自动回应",
    usage="自动回应",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_session",
    ),
)


class Reaction(BaseModel):
    user: str
    reactions: list[str]


class Config(BaseModel):
    reaction: list[Reaction] = []

    @property
    def reaction_users(self) -> set[str]:
        return {reaction.user for reaction in self.reaction}

    def get_reactions(self, user: str) -> list[str]:
        for reaction in self.reaction:
            if reaction.user == user:
                return reaction.reactions
        return []


config = get_plugin_config(Config)


def _rule_bubble(target: MsgTarget, event: Event) -> bool:
    if target.private:
        return False
    text = event.get_message().extract_plain_text()
    return check_bubble_word(text)


bubble = on_message(_rule_bubble)


@bubble.handle()
async def handle_bubble(bot: V11Bot, event: Event, session: EventSession) -> None:
    api = cast("V11API", get_api_class(bot)(bot, event, session, {}))
    with contextlib.suppress(ActionFailed):
        await api.set_reaction(38, api.mid)


def _rule(bot: Bot, event: Event, target: MsgTarget, state: T_State) -> bool:
    if target.private:
        return False

    user_id = event.get_user_id()
    adapter = bot.type.split(maxsplit=1)[0].lower()
    if user := {user_id, f"{adapter}:{user_id}"} & config.reaction_users:
        state["reactions"] = config.get_reactions(user.pop())
        return True

    return False


matcher = on_message(rule=_rule, block=False)


@matcher.handle()
async def _(bot: Bot, event: Event, session: EventSession, state: T_State) -> None:
    if not (reactions := state["reactions"]):
        return

    api = get_api_class(bot)(bot, event, session, {})
    if not (set_reaction := getattr(api, "set_reaction", None)):
        return

    with contextlib.suppress(ActionFailed):
        for reaction in reactions:
            await set_reaction(reaction, api.mid)
            await anyio.sleep(0.5)
