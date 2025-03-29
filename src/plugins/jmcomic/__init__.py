from collections.abc import Awaitable, Callable
from typing import Annotated

from nonebot import logger, require
from nonebot.adapters.onebot import v11
from nonebot.adapters.onebot.v11 import Message as V11Msg
from nonebot.adapters.onebot.v11 import MessageSegment as V11Seg
from nonebot.exception import ActionFailed
from nonebot.params import Depends
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .jm_option import check_photo, download_album_pdf, download_image, get_album_detail
from .utils import abatched

__plugin_meta__ = PluginMetadata(
    name="jmcomic",
    description="jmcomic",
    usage="/jm <id:int>",
)


matcher = on_alconna(
    Alconna("jm", Args["album_id", int]),
    permission=TrustedUser,
)


async def check_lagrange(bot: v11.Bot) -> None:
    info = await bot.get_version_info()
    if "lagrange" not in str(info.get("app_name", "unkown")).lower():
        matcher.skip()


type SendFunc = Callable[[list[V11Seg]], Awaitable[object]]


def send_func(
    bot: v11.Bot, event: v11.PrivateMessageEvent | v11.GroupMessageEvent
) -> SendFunc:
    return (
        (lambda m: bot.send_group_forward_msg(group_id=event.group_id, messages=m))
        if isinstance(event, v11.GroupMessageEvent)
        else (lambda m: bot.send_private_forward_msg(user_id=event.user_id, messages=m))
    )


@matcher.assign("album_id", parameterless=[Depends(check_lagrange)])
async def _(album_id: int, send: Annotated[SendFunc, Depends(send_func)]) -> None:
    try:
        album = await get_album_detail(album_id)
    except Exception as err:
        await matcher.finish(V11Seg.text(f"获取信息失败：{err}"))

    await matcher.send(
        V11Seg.text(
            f"标题：{album.title}\n"
            f"作者：{album.author}\n"
            f"标签：{', '.join(album.tags)}\n"
        )
    )

    segs = (
        V11Seg.node_custom(
            user_id=10086,
            nickname=f"P_{p}_{i}",
            content=V11Msg(V11Seg.image(await download_image(image))),
        )
        for p, photo in enumerate(album, 1)
        for i, image in enumerate(await check_photo(photo), 1)
    )

    try:
        async for nodes in abatched(segs, 50):
            await send(nodes)
    except ActionFailed as err:
        logger.opt(exception=err).warning(f"发送失败：{err}")
        await matcher.finish(V11Seg.text(f"发送失败：{err}"))

    await matcher.finish()


@matcher.assign("album_id")
async def _(album_id: int) -> None:
    async with download_album_pdf(album_id) as pdf_file:
        await UniMessage.file(path=pdf_file).finish()
