import itertools
from functools import partial

from nonebot import require
from nonebot.adapters.onebot import v11
from nonebot.adapters.onebot.v11 import MessageSegment as V11Seg
from nonebot.exception import ActionFailed
from nonebot.params import Depends
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_alconna")
require("nonebot_plugin_localstore")
from nonebot_plugin_alconna import Alconna, Args, UniMessage, on_alconna

from .jm_option import download_album_pdf, get_album_detail

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
    try:
        detail = await get_album_detail(album_id)
    except Exception as err:
        await matcher.finish(V11Seg.text(f"获取信息失败：{err}"))

    segs = [V11Seg.image(image.download_url) for photo in detail for image in photo]

    await matcher.send(
        V11Seg.text(
            f"标题：{detail.title}\n"
            f"作者：{detail.author}\n"
            f"标签：{', '.join(detail.tags)}\n"
            f"页数：{len(segs)}\n"
        )
    )

    if isinstance(event, v11.GroupMessageEvent):
        send = partial(bot.send_group_forward_msg, group_id=event.group_id)
    else:
        send = partial(bot.send_private_forward_msg, user_id=event.user_id)

    try:
        for nodes in itertools.batched(segs, 50):
            await send(messages=nodes)
    except ActionFailed as err:
        await matcher.finish(V11Seg.text(f"发送失败：{err}"))

    await matcher.finish()


@matcher.assign("album_id")
async def _(album_id: int) -> None:
    async with download_album_pdf(album_id) as pdf_file:
        await UniMessage.file(path=pdf_file).send()
