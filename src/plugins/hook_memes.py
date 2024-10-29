from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="hook_memes",
    description="Hook memes plugin",
    usage="None",
    type="application",
    supported_adapters={"~onebot.v11"},
)

disabled_group: set[int] = {429379849}


@run_preprocessor
async def hook_memes(event: GroupMessageEvent, matcher: Matcher) -> None:
    if (
        matcher.plugin_name == "nonebot_plugin_memes_api"
        and event.group_id in disabled_group
    ):
        raise IgnoredException(f"群 {event.group_id} 内禁用 memes")
