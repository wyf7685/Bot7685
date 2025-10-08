import json
from typing import TYPE_CHECKING

from nonebot import logger
from nonebot.adapters.onebot import v11
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Segment,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage, reply_fetch

from src.plugins.upload_cos import upload_cos

from ..adapter import get_sender
from ..adapters.onebot11 import MessageConverter
from ..database import get_cache_value
from ..utils import guess_url_type

if TYPE_CHECKING:
    from nonebot.adapters import Bot

    from .depends import MsgTarget


async def url_to_image(url: str) -> Image | None:
    if (info := await guess_url_type(url)) is None:
        return None

    try:
        url = await upload_cos(url, f"{hash(url)}.{info.extension}")
    except Exception as err:
        logger.opt(exception=err).debug("上传图片失败，使用原始链接")

    logger.debug(f"上传图片: {url}")
    return Image(url=url, mimetype=info.mime)


alc = Alconna(
    "forward",
    Subcommand(
        "cache",
        alias={"c"},
        help_text="缓存合并转发消息",
    ),
    Subcommand(
        "load",
        Args["fwd_id#合并转发ID", str],
        alias={"l"},
        help_text="加载合并转发消息",
    ),
    meta=CommandMeta(
        description="处理合并转发消息",
        fuzzy_match=True,
    ),
)

matcher = on_alconna(
    alc,
    use_cmd_start=True,
    block=True,
    extensions=[TelegramSlashExtension()],
)


@matcher.assign("cache")
async def _(bot: v11.Bot, event: v11.Event) -> None:
    reply = await reply_fetch(event, bot)
    if reply is None:
        await UniMessage.text("请回复合并转发消息以使用此命令").finish(reply_to=True)

    if not reply.msg or not isinstance(reply.msg, v11.Message):
        await UniMessage.text("获取引用消息失败").finish(reply_to=True)

    seg = reply.msg[0]
    if "content" not in seg.data:
        await UniMessage.text("无法获取合并转发消息内容").finish(reply_to=True)

    id_ = seg.data["id"]
    content = seg.data["content"]

    if not await MessageConverter(bot).cache_forward(id_, content):
        await UniMessage.text("缓存合并转发消息失败").finish(reply_to=True)

    await UniMessage.text(f"缓存合并转发消息成功: {id_}").finish(reply_to=True)


async def _convert_image(segment: Segment) -> bool | Segment:
    if not isinstance(segment, Image):
        return True

    return (
        converted
        if segment.url is not None and (converted := await url_to_image(segment.url))
        else Text("[图片]")
    )


@matcher.assign("load")
async def _(bot: Bot, target: MsgTarget, fwd_id: str) -> None:
    cache = await get_cache_value(v11.Adapter.get_name(), f"forward_{fwd_id}")

    if cache is None:
        await UniMessage.text("未找到合并转发消息").finish(reply_to=True)

    cache_data = json.loads(cache)
    send = get_sender(bot).send

    for item in cache_data:
        nick = item["nick"]
        msg = await UniMessage.load(item["msg"]).transform_async(_convert_image)
        msg.insert(0, Text(f"{nick}\n\n"))
        try:
            await send(bot, target, msg)
        except Exception as err:
            await UniMessage.text(f"发送消息失败: {err}").finish()

    await UniMessage.text(f"加载合并转发消息成功: {fwd_id}").finish(reply_to=True)
