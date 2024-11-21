import asyncio

from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)

from ..database import PipeDAO, display_pipe
from .depends import MsgTarget

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
