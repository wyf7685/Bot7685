import json

from nonebot.adapters import Bot
from nonebot.adapters.onebot import v11
from nonebot_plugin_alconna import Alconna, Args, CommandMeta, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import Image, Reply, Text, UniMessage, reply_fetch

from ..database import KVCacheDAO
from ..processor import get_processor
from ..processor.onebot11 import MessageProcessor as V11MessageProcessor
from ..processor.onebot11 import url_to_image

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

matcher = on_alconna(alc)


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

    if not await V11MessageProcessor(bot).cache_forward(id_, content):
        await UniMessage.text("缓存合并转发消息失败").finish(reply_to=True)

    await UniMessage.text(f"缓存合并转发消息成功: {id_}").finish(reply_to=True)


@matcher.assign("load")
async def _(bot: Bot, fwd_id: str) -> None:
    cache = await KVCacheDAO().get_value(v11.Adapter.get_name(), f"forward_{fwd_id}")

    if cache is None:
        await UniMessage.text("未找到合并转发消息").finish(reply_to=True)

    cache_data = json.loads(cache)
    processor = get_processor(bot.type)
    msg_ids: dict[str, str] = {}

    for item in cache_data:
        nick = item["nick"]
        msg = UniMessage.load(item["msg"])

        for idx in range(len(msg)):
            seg = msg[idx]
            if isinstance(seg, Image) and seg.url:
                msg[idx] = await url_to_image(seg.url)
            elif isinstance(seg, Reply):
                seg.id = msg_ids[seg.id]

        msg.insert(0, Text(f"{nick}\n\n"))
        try:
            receipt = await msg.send()
        except Exception as err:
            await UniMessage.text(f"发送消息失败: {err}").finish()

        msg_ids[item["seq"]] = await processor.extract_msg_id(receipt.msg_ids)

    await UniMessage.text(f"加载合并转发消息成功: {fwd_id}").finish(reply_to=True)
