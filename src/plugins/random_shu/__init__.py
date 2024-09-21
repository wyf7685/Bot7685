from datetime import timedelta

from nonebot import on_fullmatch, on_notice, on_startswith
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, MessageSegment
from nonebot.adapters.onebot.v11.event import GroupMessageEvent
from nonebot.log import logger
from nonebot.matcher import Matcher

from .constant import emoji_weight_actions
from .data import Data
from .event import GroupMsgEmojiLikeEvent
from .router import setup_router

url = setup_router()


def handle_response(msg_id: int, user_id: int, item: Data) -> type[Matcher]:
    logger.debug(f"{msg_id=}, {user_id=}, {item=}")

    weight, action = 0, ""

    async def rule(event: GroupMsgEmojiLikeEvent) -> bool:
        if (
            event.message_id != msg_id or event.user_id != user_id or not event.likes
        ) or (
            (emoji_id := int(event.likes.pop(0).emoji_id))
            and emoji_id not in emoji_weight_actions
        ):
            return False

        nonlocal weight, action
        weight, action = emoji_weight_actions[emoji_id]
        return True

    async def handler() -> None:
        await item.add_weight(weight)
        logger.opt(colors=True).info(
            f"黍泡泡 [<le>{item.text}</le>] 权重{action} {abs(weight)}, "
            f"当前权重: <c>{item.weight}</c>"
        )

    return on_notice(
        rule=rule,
        handlers=[handler],
        temp=True,
        expire_time=timedelta(seconds=30),
    )


@on_fullmatch("黍泡泡权重", priority=1, block=True).handle()
async def _(bot: Bot, event: MessageEvent) -> None:
    msg = Message("在黍泡泡消息上进行表情回应, 可以修改对应词条的权重\n\n")
    for emoji_id, (weight, action) in emoji_weight_actions.items():
        msg += MessageSegment.face(emoji_id) + f" {action} {abs(weight)} 权重\n"
    await bot.send(event, msg)


@on_startswith(("抽黍泡泡", "黍泡泡"), priority=2).handle()
async def _(bot: Bot, event: MessageEvent) -> None:
    item = await Data.choose()
    img = MessageSegment.image(file=str(url.with_query({"key": item.name})))
    img.data["summary"] = item.text
    send_result = await bot.send(event, MessageSegment.reply(event.message_id) + img)
    if isinstance(event, GroupMessageEvent):
        # 此处消息ID+1 为 NapCatQQ 的逻辑问题
        # 获取的消息ID与表情回应的上报ID不一致, 差值为 1
        # 暂时使用该方法纠正, 等 NapCatQQ 修复后再修改
        matcher = handle_response(send_result["message_id"] + 1, event.user_id, item)
        logger.debug(f"创建 Callback: {matcher}")
