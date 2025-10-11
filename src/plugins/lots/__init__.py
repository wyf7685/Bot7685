import contextlib

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, on_alconna
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_alconna.uniseg import At, message_reaction

from .depends import LotsTarget
from .lots_data import get_lots_msg

__plugin_meta__ = PluginMetadata(
    name="lots",
    description="御神签",
    usage="提供御神签功能",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

lots = on_alconna(
    Alconna("御神签", Args["target?", At]),
    extensions=[TelegramSlashExtension()],
)


@lots.handle()
async def _(target: LotsTarget) -> None:
    msg, emoji = get_lots_msg(target)
    await msg.send(reply_to=True)

    with contextlib.suppress(Exception):
        await message_reaction(emoji)
