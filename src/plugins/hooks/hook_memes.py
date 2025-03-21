from nonebot import get_plugin_config
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel


class Config(BaseModel):
    memes_disabled_group: set[int] = set()


__plugin_meta__ = PluginMetadata(
    name="hook_memes",
    description="Hook memes plugin",
    usage="None",
    type="application",
    config=Config,
    supported_adapters={"~onebot.v11"},
)


disabled = get_plugin_config(Config).memes_disabled_group


@run_preprocessor
async def hook_memes(event: GroupMessageEvent, matcher: Matcher) -> None:
    if matcher.plugin_name == "nonebot_plugin_memes_api" and event.group_id in disabled:
        raise IgnoredException(f"群 {event.group_id} 内禁用 memes")
