from typing import Any

from nonebot import require
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, Subcommand, on_alconna
from nonebot_plugin_localstore import get_plugin_config_file

__plugin_meta__ = PluginMetadata(
    name="meow",
    description="meow?",
    usage="meow!",
    type="application",
    supported_adapters={"~onebot.v11"},
)


def fix_meow_word(word: str) -> str:
    word = word.rstrip()
    if (ls := word.lstrip()) != word:
        word = f" {ls}"
    return word


enabled_flag = get_plugin_config_file("meow.enabled").resolve()
enabled = enabled_flag.exists()
word_file = get_plugin_config_file("meow.txt").resolve()
if not word_file.exists():
    word_file.write_text(meow_word := "喵")
else:
    meow_word = fix_meow_word(word_file.read_text())


toggle = on_alconna(
    Alconna(
        "meow",
        Subcommand("enable", alias={"e"}, help_text="启用"),
        Subcommand("disable", alias={"d"}, help_text="禁用"),
        Subcommand("set", Args["word#内容", str], alias={"s"}, help_text="设置"),
        meta=CommandMeta(
            description="meow?",
            usage="/meow <enable|disable>",
        ),
    )
)


@toggle.assign("enable")
def handle_meow_enable() -> None:
    global enabled

    if not enabled:
        enabled_flag.touch()
        enabled = True


@toggle.assign("disable")
def handle_meow_disable() -> None:
    global enabled

    if enabled:
        enabled_flag.unlink()
        enabled = False


@toggle.assign("set")
async def handle_meow_set(word: str) -> None:
    global meow_word

    word = fix_meow_word(word)
    word_file.write_text(word)
    meow_word = word


SEND_MSG_API = "send_msg", "send_group_msg", "send_private_msg"


@BaseBot.on_calling_api
async def _(bot: BaseBot, api: str, data: dict[str, Any]) -> None:
    if not enabled:
        return

    if not (
        isinstance(bot, Bot)
        and api in SEND_MSG_API
        and (message := data.get("message"))
        and isinstance(message, list)
    ):
        return

    if isinstance(message, Message):
        if isinstance(seg := message[-1], MessageSegment) and seg.type == "text":
            seg.data["text"] += meow_word
    elif isinstance(seg := message[-1], dict) and seg.get("type") == "text":
        seg["data"]["text"] += meow_word
