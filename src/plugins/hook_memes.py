from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import run_preprocessor


disabled_group: set[int] = {429379849}


@run_preprocessor
async def hook_memes(event: GroupMessageEvent, matcher: Matcher):
    if (
        matcher.plugin_name == "nonebot_plugin_memes"
        and event.group_id in disabled_group
    ):
        raise IgnoredException(f"群 {event.group_id} 内禁用 memes")
