from nonebot import require
from nonebot.adapters import Bot as BaseBot
from nonebot.adapters.onebot.v11 import Bot, Message
from nonebot.plugin import PluginMetadata
from pydantic import BaseModel

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, Subcommand, on_alconna
from nonebot_plugin_localstore import get_plugin_config_file

from src.utils import ConfigModelFile

__plugin_meta__ = PluginMetadata(
    name="meow",
    description="meow?",
    usage="meow!",
    type="application",
    supported_adapters={"~onebot.v11"},
)


@ConfigModelFile.from_model(get_plugin_config_file("meow.json"))
class config(BaseModel):  # noqa: N801
    word: str = "喵"
    enabled: bool = False


def fix_meow_word(word: str) -> str:
    word = word.rstrip()
    if (ls := word.lstrip()) != word:
        word = f" {ls}"
    return word


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
    config.load().enabled = True


@toggle.assign("disable")
def handle_meow_disable() -> None:
    config.load().enabled = False


@toggle.assign("set")
async def handle_meow_set(word: str) -> None:
    config.load().word = fix_meow_word(word)


@toggle.assign("~")
async def handle_save_config() -> None:
    config.save()


SEND_MSG_API = "send_msg", "send_group_msg", "send_private_msg"


@BaseBot.on_calling_api
async def _(bot: BaseBot, api: str, data: dict[str, object]) -> None:
    if not config.load().enabled:
        return

    if not (
        isinstance(bot, Bot)
        and api in SEND_MSG_API
        and (message := data.get("message"))
        and isinstance(message, list)
    ):
        return

    if isinstance(message, Message):
        if (seg := message[-1]).type == "text":
            seg.data["text"] += config.load().word
    elif isinstance(seg := message[-1], dict) and seg.get("type") == "text":
        seg["data"]["text"] += config.load().word
