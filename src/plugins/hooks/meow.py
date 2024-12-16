from typing import Any

from nonebot import require
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.onebot.v11 import Bot, Message, MessageSegment

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, Subcommand, on_alconna
from nonebot_plugin_localstore import get_plugin_config_file

enabled_flag = get_plugin_config_file("meow.enabled").resolve()
enabled = enabled_flag.exists()
word_file = get_plugin_config_file("meow.txt").resolve()
if not word_file.exists():
    word_file.write_text(meow_word := "喵")
else:
    meow_word = word_file.read_text().strip()

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

    word_file.write_text(word)
    meow_word = word


@BaseBot.on_calling_api
async def _(bot: BaseBot, api: str, data: dict[str, Any]) -> None:
    if not enabled:
        return

    if not isinstance(bot, Bot):
        return

    if api not in {"send_msg", "send_group_msg", "send_private_msg"}:
        return

    if "message" not in data:
        return

    message = data["message"]

    if (
        isinstance(message, Message)
        and message
        and isinstance(seg := message[-1], MessageSegment)
        and seg.type == "text"
    ):
        seg.data["text"] += meow_word
    elif (
        isinstance(message, list)
        and message
        and isinstance(seg := message[-1], dict)
        and seg.get("type") == "text"
    ):
        seg["data"]["text"] += meow_word
