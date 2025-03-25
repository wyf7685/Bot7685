from nonebot import require
from nonebot.adapters.onebot import v11
from nonebot.adapters.onebot.v11 import Message as V11Msg
from nonebot.adapters.onebot.v11 import MessageSegment as V11Seg
from nonebot.params import Depends
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna

from .jm_option import (
    DOWNLOAD_DIR,
    download_album,
    download_album_pdf,
    get_album_detail,
)

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <id:int>",
)


matcher = on_alconna(Alconna("jm", Args["album_id", int]))


async def check_lagrange(bot: v11.Bot) -> None:
    info = await bot.get_version_info()
    if "lagrange" not in str(info.get("app_name", "unkown")).lower():
        matcher.skip()


@matcher.assign("album_id", parameterless=[Depends(check_lagrange)])
async def _(
    bot: v11.Bot,
    event: v11.PrivateMessageEvent | v11.GroupMessageEvent,
    album_id: int,
) -> None:
    detail = await get_album_detail(album_id)
    await matcher.send(
        V11Seg.text(
            f"标题：{detail.title}\n"
            f"作者：{detail.author}\n"
            f"标签：{', '.join(detail.tags)}\n"
            f"页数：{detail.page_count}\n"
        )
    )

    fwds: list[list[V11Seg]] = []
    nodes: list[V11Seg] = []

    await download_album(album_id)
    for idx, file in enumerate((DOWNLOAD_DIR / str(album_id)).iterdir(), 1):
        msg = V11Msg(V11Seg.image(file.read_bytes()))
        node = V11Seg.node_custom(10086, f"P {idx}", msg)
        nodes.append(node)
        if len(nodes) >= 50:
            fwds.append(nodes.copy())
            nodes.clear()
    if nodes:
        fwds.append(nodes.copy())

    for nodes in fwds:
        if isinstance(event, v11.GroupMessageEvent):
            await bot.send_group_forward_msg(group_id=event.group_id, messages=nodes)
        else:
            await bot.send_private_forward_msg(user_id=event.user_id, messages=nodes)

    await matcher.finish()


@matcher.assign("album_id")
async def _(album_id: int) -> None:
    async with download_album_pdf(album_id) as pdf_file:
        await UniMessage.file(path=pdf_file).send()
