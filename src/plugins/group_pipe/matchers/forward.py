import json

from nonebot import logger, require
from nonebot.adapters import Bot
from nonebot.adapters.onebot import v11
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, Subcommand, on_alconna
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_alconna.uniseg import Image, Text, UniMessage, reply_fetch

require("src.plugins.upload_cos")
from src.plugins.upload_cos import upload_from_url

from ..database import KVCacheDAO
from ..processor import get_processor
from ..processor.onebot11 import MessageConverter
from ..utils import guess_url_type
from .depends import MsgTarget


async def url_to_image(url: str) -> Image | None:
    if (info := await guess_url_type(url)) is None:
        return None

    try:
        url = await upload_from_url(url, f"{hash(url)}.{info.extension}")
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


@matcher.assign("load")
async def _(bot: Bot, target: MsgTarget, fwd_id: str) -> None:
    cache = await KVCacheDAO().get_value(v11.Adapter.get_name(), f"forward_{fwd_id}")

    if cache is None:
        await UniMessage.text("未找到合并转发消息").finish(reply_to=True)

    cache_data = json.loads(cache)
    processor = get_processor(bot)

    for item in cache_data:
        nick = item["nick"]
        msg = UniMessage.load(item["msg"])

        for idx in range(len(msg)):
            seg = msg[idx]
            if isinstance(seg, Image) and seg.url:
                msg[idx] = await url_to_image(seg.url) or Text("[图片]")

        msg.insert(0, Text(f"{nick}\n\n"))
        try:
            await processor.send(
                dst_bot=bot,
                target=target,
                msg=msg,
            )
        except Exception as err:
            await UniMessage.text(f"发送消息失败: {err}").finish()

    await UniMessage.text(f"加载合并转发消息成功: {fwd_id}").finish(reply_to=True)
