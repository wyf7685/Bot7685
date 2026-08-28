from typing import Annotated

from arclet.alconna import Alconna, AllParam, Args, CommandMeta, Option
from nonebot_plugin_alconna import (
    AlconnaMatch,
    Match,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.reply import ReplyRecordExtension

type ParsedContent = Annotated[Match[UniMessage], AlconnaMatch("content")]

matcher = on_alconna(
    Alconna(
        "zssm",
        Option(
            "--model|-m",
            Args["model_alias#模型别名", str],
            help_text="本次调用使用指定模型别名",
        ),
        Args["content?", AllParam],
        meta=CommandMeta(
            description="群聊上下文增强的工具调用式大语言模型助手",
            usage="zssm [-m <模型别名>] [内容]",
        ),
    ),
    extensions=[ReplyRecordExtension()],
    use_cmd_start=True,
    block=True,
)


__all__ = ["ParsedContent", "matcher"]
