from collections.abc import Sequence
from typing import Any

from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Subcommand,
    Target,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension

from src.plugins.cache import get_cache

from ..database import (
    PipeTuple,
    create_pipe,
    delete_pipe,
    display_pipe,
    get_linked_pipes,
    get_pipes,
)
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


pipe_cmd = on_alconna(
    alc,
    _rule_is_group,
    permission=SUPERUSER,
    extensions=[TelegramSlashExtension()],
    use_cmd_start=True,
)


def show_pipes(
    listen: Sequence[PipeTuple] | None = None,
    target: Sequence[PipeTuple] | None = None,
) -> str:
    idx = 1
    msg = ""
    if listen:
        for pipe in listen:
            t = pipe.target
            msg += f"{idx}. ==> <{t.adapter}: {t.id}>\n"
            idx += 1
    if target:
        for pipe in target:
            t = pipe.listen
            msg += f"{idx}. <== <{t.adapter}: {t.id}>\n"
            idx += 1
    return msg.rstrip("\n")


@pipe_cmd.assign("list.listen")
async def assign_list_listen(target: MsgTarget) -> None:
    pipes = await get_pipes(listen=target)
    if not pipes:
        await UniMessage.text("没有监听当前群组的管道").finish(reply_to=True)

    msg = "监听当前群组的管道:\n" + show_pipes(listen=pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list.target")
async def assign_list_target(target: MsgTarget) -> None:
    pipes = await get_pipes(target=target)
    if not pipes:
        await UniMessage.text("没有目标为当前群组的管道").finish(reply_to=True)

    msg = "目标为当前群组的管道:\n" + show_pipes(target=pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list")
async def assign_list(target: MsgTarget) -> None:
    listen_pipes, target_pipes = await get_linked_pipes(target)
    if not listen_pipes and not target_pipes:
        await UniMessage.text("没有链接到当前群组的管道").finish(reply_to=True)

    msg = "当前群组的管道:\n" + show_pipes(listen_pipes, target_pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


cache = get_cache[int, dict[str, Any]]("pipe:link")


@pipe_cmd.assign("create")
async def assign_create(target: MsgTarget) -> None:
    key = hash(target)
    await cache.set(key, target.dump(), ttl=60 * 5)

    await (
        UniMessage.text("请在5分钟内向目标群组中发送以下命令:\n")
        .text(f"/pipe link {key}")
        .finish(reply_to=True)
    )


@pipe_cmd.assign("link")
async def assign_link(target: MsgTarget, code: int) -> None:
    if not (data := await cache.get(code)):
        await UniMessage.text("链接码无效或已过期").finish(reply_to=True)

    listen = Target.load(data)
    await create_pipe(listen, target)
    msg = f"管道创建成功:\n{display_pipe(listen, target)}"
    await UniMessage.text(msg).finish(reply_to=True)


@pipe_cmd.assign("remove")
async def assign_remove(target: MsgTarget, idx: int) -> None:
    listen_pipes, target_pipes = await get_linked_pipes(target)
    if idx < 1 or idx > len(listen_pipes) + len(target_pipes):
        await UniMessage.text("管道序号无效").finish(reply_to=True)

    pipe = (listen_pipes + target_pipes)[idx - 1]
    await delete_pipe(pipe)
    (listen_pipes if pipe in listen_pipes else target_pipes).remove(pipe)

    msg = (
        "管道删除成功:\n"
        f"{display_pipe(pipe.listen, pipe.target)}\n\n"
        "当前群组的管道:\n" + show_pipes(listen_pipes, target_pipes)
    )
    await UniMessage.text(msg).finish(reply_to=True)
