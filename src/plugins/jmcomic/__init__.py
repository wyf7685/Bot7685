from nonebot import require
from nonebot.plugin import PluginMetadata
from nonebot.utils import run_sync

import jmcomic

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna

from .jm_option import PDF_DIR, option

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <id:int>",
)


matcher = on_alconna(Alconna("jm", Args["album_id", int]))


@matcher.assign("album_id")
async def _(album_id: int) -> None:
    downloader = jmcomic.new_downloader(option)
    detail = await run_sync(downloader.download_album)(album_id)
    pdf_file = PDF_DIR / f"{detail.album_id}.pdf"
    await UniMessage.file(path=pdf_file).send()
