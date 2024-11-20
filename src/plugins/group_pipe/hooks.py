import asyncio

from nonebot import logger
from nonebot.adapters import Bot, Event, Message
from nonebot.message import event_postprocessor
from nonebot_plugin_alconna import (
    FallbackStrategy,
    Target,
    UniMessage,
)
from nonebot_plugin_uninfo import get_session

from . import matchers as matchers
from .database import MsgIdCacheDAO, PipeDAO, display_pipe
from .processor import get_processor


async def send_pipe_msg(
    bot: Bot,
    listen: Target,
    target: Target,
    msg_id: str,
    msg_head: str,
    msg: Message,
) -> None:
    display = display_pipe(listen, target)

    try:
        bot_ = await target.select()
    except Exception as err:
        logger.warning(f"管道: {display}")
        logger.warning(f"管道选择目标 Bot 失败: {err}")
        return

    m = UniMessage.text(msg_head)
    m.extend(await get_processor(listen.adapter)(bot, bot_).process(msg))
    logger.debug(f"发送管道: {display}")
    logger.debug(f"消息: {m}")

    try:
        receipt = await m.send(
            target=target,
            bot=bot_,
            fallback=FallbackStrategy.ignore,
        )
    except Exception as err:
        logger.warning(f"管道: {display}")
        logger.warning(f"发送管道消息失败: {err}")
        return

    dst_id = await get_processor(bot_.type).extract_msg_id(receipt.msg_ids)
    await MsgIdCacheDAO().set_dst_id(
        src_adapter=bot.type,
        src_id=msg_id,
        dst_adapter=bot_.type,
        dst_id=dst_id,
    )


@event_postprocessor
async def handle_pipe_msg(bot: Bot, event: Event) -> None:
    if event.get_type() != "message":
        return

    try:
        listen = UniMessage.get_target(event, bot)
        msg_id = UniMessage.get_message_id(event, bot)
        info = await get_session(bot, event)
    except Exception as err:
        logger.warning(f"获取消息信息失败: {err}")
        return

    if info is None:
        logger.debug("消息信息为空")
        return

    pipes = await PipeDAO().get_pipes(listen=listen)
    if not pipes:
        logger.trace("没有监听当前群组的管道")
        return

    group_name = (g := info.group or info.guild) and g.name or listen.id
    user_name = info.user.nick or info.user.name or info.user.id
    msg_head = f"[ {group_name} - {user_name} ]\n"
    msg = get_processor(listen.adapter).get_message(event)

    coros = [
        send_pipe_msg(
            bot=bot,
            listen=listen,
            target=pipe.get_target(),
            msg_id=msg_id,
            msg_head=msg_head,
            msg=msg,
        )
        for pipe in pipes
    ]
    await asyncio.gather(*coros)
