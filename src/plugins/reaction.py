import contextlib
from typing import TYPE_CHECKING, cast

import anyio
from nonebot import get_plugin_config, on_keyword, on_message, require
from nonebot.adapters import Bot, Event
from nonebot.adapters.onebot.v11 import Bot as V11Bot
from nonebot.adapters.telegram import Bot as TgBot
from nonebot.exception import ActionFailed
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_session")
from nonebot_plugin_alconna import MsgTarget
from nonebot_plugin_session import EventSession

if TYPE_CHECKING:
    from nonebot_plugin_exe_code.interface import get_api_class
    from nonebot_plugin_exe_code.interface.adapters.onebot11 import API as V11API
    from nonebot_plugin_exe_code.interface.adapters.telegram import API as TGAPI
else:
    try:
        require("src.dev.nonebot_plugin_exe_code")
        from src.dev.nonebot_plugin_exe_code.interface import get_api_class
    except Exception:
        require("nonebot_plugin_exe_code")
        from nonebot_plugin_exe_code.interface import get_api_class


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


class Config(BaseModel):
    reaction_users: set[str] = set()


config = get_plugin_config(Config)


def _rule_bubble(target: MsgTarget) -> bool:
    return not target.private


bubble = on_keyword({"冒泡", "锚抛"}, _rule_bubble)


@bubble.handle()
async def handle_bubble(bot: V11Bot, event: Event, session: EventSession) -> None:
    api = cast("V11API", get_api_class(bot)(bot, event, session, {}))
    with contextlib.suppress(ActionFailed):
        await api.set_reaction(38, api.mid)


def _rule(bot: Bot, event: Event, target: MsgTarget) -> bool:
    if target.private:
        return False

    user_id = event.get_user_id()
    adapter = bot.type.split(maxsplit=1)[0].lower()

    return any({user_id, f"{adapter}:{user_id}"} & config.reaction_users)


matcher = on_message(rule=_rule, block=False)


@matcher.handle()
async def _(bot: V11Bot, event: Event, session: EventSession) -> None:
    api = cast("V11API", get_api_class(bot)(bot, event, session, {}))
    with contextlib.suppress(ActionFailed):
        await api.set_reaction(424, api.mid)
        await anyio.sleep(0.5)
        await api.set_reaction(38, api.mid)
        await anyio.sleep(0.5)
        await api.set_reaction(285, api.mid)


@matcher.handle()
async def _(bot: TgBot, event: Event, session: EventSession) -> None:
    api = cast("TGAPI", get_api_class(bot)(bot, event, session, {}))
    with contextlib.suppress(ActionFailed):
        await api.set_reaction("🤓", api.mid)
