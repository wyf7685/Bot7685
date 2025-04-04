import anyio
from nonebot import logger
from nonebot.adapters import Bot, Event, Message
from nonebot.message import event_preprocessor
from nonebot_plugin_alconna import Target, UniMessage, get_target
from nonebot_plugin_uninfo import get_session

from .adapters import get_converter, get_sender
from .database import PipeDAO, display_pipe
from .utils import repr_unimsg


async def send_pipe_msg(
    bot: Bot,
    listen: Target,
    target: Target,
    msg_id: str,
    msg_head: UniMessage,
    msg: Message,
) -> None:
    display = display_pipe(listen, target)

    try:
        dst_bot = await target.select()
    except Exception as err:
        logger.warning(f"管道: {display}")
        logger.warning(f"管道选择目标 Bot 失败: {err}")
        return

    unimsg = msg_head + await get_converter(bot, dst_bot).convert(msg)
    logger.debug(f"发送管道: {display}")
    logger.debug(f"消息: {repr_unimsg(unimsg)}")

    try:
        await get_sender(dst_bot).send(
            dst_bot=dst_bot,
            target=target,
            msg=unimsg,
            src_type=bot.type,
            src_id=msg_id,
        )
    except Exception as err:
        logger.warning(f"管道: {display}")
        logger.warning(f"发送管道消息失败: {err}")
        logger.opt(exception=err).debug(err)
        return


@event_preprocessor
async def handle_pipe_msg(bot: Bot, event: Event) -> None:
    if event.get_type() != "message":
        return

    try:
        listen = get_target(event, bot)
        info = await get_session(bot, event)
    except Exception as err:
        logger.trace(f"获取消息信息失败: {err}")
        return

    if info is None:
        logger.trace("无法获取群组信息，跳过管道消息处理")
        return

    pipes = await PipeDAO().get_pipes(listen=listen)
    if not pipes:
        logger.trace("没有监听当前群组的管道")
        return

    converter = get_converter(listen.adapter)
    msg = converter.get_message(event)
    if msg is None:
        logger.trace("无法获取消息内容，跳过管道消息处理")
        return

    try:
        msg_id = converter.get_message_id(event, bot)
    except Exception as err:
        logger.trace(f"获取消息 ID 失败: {err}")
        return

    group_name = ((g := info.group or info.guild) and g.name) or listen.id
    user_name = info.user.nick or info.user.name or info.user.id
    msg_head = UniMessage.text(f"[ {group_name} - {user_name} ]\n")

    async def _send(target: Target) -> None:
        logger.debug(f"管道转发: {display_pipe(listen, target)}")
        await send_pipe_msg(bot, listen, target, msg_id, msg_head, msg)

    # Avoid unnessary task group
    if len(pipes) == 1:
        await _send(pipes.pop().target)
        return

    async with anyio.create_task_group() as tg:
        for pipe in pipes:
            tg.start_soon(_send, pipe.target)
