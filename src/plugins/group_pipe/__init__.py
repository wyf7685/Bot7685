import asyncio
from typing import Annotated

from nonebot import logger, require
from nonebot.adapters import Bot, Event, Message
from nonebot.matcher import Matcher
from nonebot.message import event_postprocessor
from nonebot.params import Depends
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    FallbackStrategy,
    Match,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import get_session

from .database import MsgIdCacheDAO, PipeDAO, display_pipe
from .processor import get_processor

__plugin_meta__ = PluginMetadata(
    name="group_pipe",
    description="群组管道",
    usage="pipe --help",
    type="application",
    supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna"),
)

alc = Alconna(
    "pipe",
    Subcommand(
        "list",
        Subcommand("listen", help_text="仅列出监听当前群组的管道"),
        Subcommand("target", help_text="仅列出目标为当前群组的管道"),
        alias={"ls"},
        help_text="列出当前群组的所有管道",
    ),
    Subcommand(
        "create",
        alias={"c"},
        help_text="创建一个监听当前群组的管道",
    ),
    Subcommand(
        "link",
        Args["code#链接码", int],
        help_text="将一个管道链接到当前群组",
    ),
    Subcommand(
        "remove",
        Args["idx#管道序号", int],
        alias={"r", "rm"},
        help_text="删除一个当前群组管道",
    ),
    meta=CommandMeta(
        description="群组管道",
        usage="pipe --help",
        example="pipe list\npipe create\npipe link <链接码>\npipe remove <管道序号>",
        author="wyf7685",
        fuzzy_match=True,
    ),
)


async def _target(bot: Bot, event: Event) -> Target:
    try:
        return UniMessage.get_target(event, bot)
    except Exception:
        Matcher.skip()


MsgTarget = Annotated[Target, Depends(_target, use_cache=True)]


async def _rule_is_group(target: MsgTarget) -> bool:
    return not target.private


pipe_cmd = on_alconna(alc, _rule_is_group, permission=SUPERUSER, use_cmd_start=True)


@pipe_cmd.assign("list.listen")
async def assign_list_listen(target: MsgTarget) -> None:
    pipes = await PipeDAO().get_pipes(listen=target)
    if not pipes:
        await UniMessage.text("没有监听当前群组的管道").finish(reply_to=True)

    msg = "监听当前群组的管道:\n"
    for idx, pipe in enumerate(pipes, 1):
        t = pipe.get_target()
        msg += f"{idx}. ==> <{t.adapter}: {t.id}>\n"
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list.target")
async def assign_list_target(target: MsgTarget) -> None:
    pipes = await PipeDAO().get_pipes(target=target)
    if not pipes:
        await UniMessage.text("没有目标为当前群组的管道").finish(reply_to=True)

    msg = "目标为当前群组的管道:\n"
    for idx, pipe in enumerate(pipes, 1):
        t = pipe.get_listen()
        msg += f"{idx}. <== <{t.adapter}: {t.id}>\n"
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list")
async def assign_list(target: MsgTarget) -> None:
    listen_pipes, target_pipes = await PipeDAO().get_linked_pipes(target)
    if not listen_pipes and not target_pipes:
        await UniMessage.text("没有链接到当前群组的管道").finish(reply_to=True)

    msg = "当前群组的管道:\n"
    for idx, pipe in enumerate(listen_pipes, 1):
        t = pipe.get_target()
        msg += f"{idx}. ==> <{t.adapter}: {t.id}>\n"
    for idx, pipe in enumerate(target_pipes, len(listen_pipes) + 1):
        t = pipe.get_listen()
        msg += f"{idx}. <== <{t.adapter}: {t.id}>\n"
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


pipe_create_cache: dict[int, Target] = {}


@pipe_cmd.assign("create")
async def assign_create(target: MsgTarget) -> None:
    key = hash(target)
    pipe_create_cache[key] = target
    asyncio.get_event_loop().call_later(60 * 5, pipe_create_cache.pop, key, None)
    await (
        UniMessage.text("请在5分钟内向目标群组中发送以下命令:\n")
        .text(f"/pipe link {key}")
        .finish(reply_to=True)
    )


@pipe_cmd.assign("link")
async def assign_link(target: MsgTarget, code: Match[int]) -> None:
    listen = pipe_create_cache.pop(code.result, None)
    if listen is None:
        await UniMessage.text("链接码无效或已过期").finish(reply_to=True)

    await PipeDAO().create_pipe(listen, target)
    msg = f"管道创建成功:\n{display_pipe(listen,target)}"
    await UniMessage.text(msg).finish(reply_to=True)


@pipe_cmd.assign("remove")
async def assign_remove(target: MsgTarget, idx: Match[int]) -> None:
    listen_pipes, target_pipes = await PipeDAO().get_linked_pipes(target)
    pipes = [*listen_pipes, *target_pipes]
    if idx.result < 1 or idx.result > len(pipes):
        await UniMessage.text("管道序号无效").finish(reply_to=True)

    pipe = pipes[idx.result - 1]
    listen, target = pipe.get_listen(), pipe.get_target()
    await PipeDAO().delete_pipe(pipe)
    msg = f"管道删除成功:\n{display_pipe(listen, target)}"
    await UniMessage.text(msg).finish(reply_to=True)


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
