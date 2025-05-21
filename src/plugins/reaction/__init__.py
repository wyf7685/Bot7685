import contextlib

import anyio
from nonebot import get_plugin_config, on_message, require
from nonebot.adapters import Bot, Event
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State
from pydantic import BaseModel

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import MsgTarget, message_reaction

from .bubble_check import check_bubble_word

__plugin_meta__ = PluginMetadata(
    name="reaction",
    description="自动回应",
    usage="自动回应",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
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
async def handle_bubble() -> None:
    with contextlib.suppress(ActionFailed):
        await message_reaction("38")


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
async def _(state: T_State) -> None:
    if not (reactions := state["reactions"]):
        return

    with contextlib.suppress(ActionFailed):
        for reaction in reactions:
            await message_reaction(str(reaction))
            await anyio.sleep(0.5)
