from typing import Annotated

from arclet.alconna import Alconna, AllParam, Args
from nonebot_plugin_alconna import (
    AlconnaMatch,
    Match,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyRecordExtension

type ParsedContent = Annotated[Match[UniMessage], AlconnaMatch("content")]

matcher = on_alconna(
    Alconna("zssm", Args["content?", AllParam]),
    extensions=[ReplyRecordExtension()],
    use_cmd_start=True,
    block=True,
)


__all__ = ["ParsedContent", "matcher"]
