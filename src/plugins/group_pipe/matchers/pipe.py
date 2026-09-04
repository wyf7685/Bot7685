import secrets
from collections.abc import Sequence

from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_uninfo.target import to_target

from src.service.cache import get_cache
from src.service.uninfo_target import (
    get_session_reference,
    persist_session_reference,
    resolve_target,
)

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
async def assign_list_listen(session: Uninfo) -> None:
    ref = await persist_session_reference(session)
    pipes = await get_pipes(listen_scene_persist_id=ref.scene_persist_id)
    if not pipes:
        await UniMessage.text("没有监听当前群组的管道").finish(reply_to=True)

    msg = "监听当前群组的管道:\n" + show_pipes(listen=pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list.target")
async def assign_list_target(session: Uninfo) -> None:
    ref = await persist_session_reference(session)
    pipes = await get_pipes(target_scene_persist_id=ref.scene_persist_id)
    if not pipes:
        await UniMessage.text("没有目标为当前群组的管道").finish(reply_to=True)

    msg = "目标为当前群组的管道:\n" + show_pipes(target=pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


@pipe_cmd.assign("list")
async def assign_list(session: Uninfo) -> None:
    ref = await persist_session_reference(session)
    listen_pipes, target_pipes = await get_linked_pipes(ref.scene_persist_id)
    if not listen_pipes and not target_pipes:
        await UniMessage.text("没有链接到当前群组的管道").finish(reply_to=True)

    msg = "当前群组的管道:\n" + show_pipes(listen_pipes, target_pipes)
    await UniMessage.text(msg.rstrip("\n")).finish(reply_to=True)


cache = get_cache("pipe:link", int)


async def _create_link_code() -> int:
    for _ in range(10):
        code = 100000 + secrets.randbelow(900000)
        if not await cache.exists(str(code)):
            return code
    raise RuntimeError("failed to allocate pipe link code")


@pipe_cmd.assign("create")
async def assign_create(session: Uninfo) -> None:
    ref = await persist_session_reference(session)
    code = await _create_link_code()
    await cache.set(str(code), ref.session_persist_id, ttl=60 * 5)

    await (
        UniMessage.text("请在5分钟内向目标群组中发送以下命令:\n")
        .text(f"/pipe link {code}")
        .finish(reply_to=True)
    )


@pipe_cmd.assign("link")
async def assign_link(session: Uninfo, code: int) -> None:
    listen_session_id = await cache.get(str(code))
    if listen_session_id is None:
        await UniMessage.text("链接码无效或已过期").finish(reply_to=True)

    listen_ref = await get_session_reference(listen_session_id)
    listen_target = await resolve_target(listen_session_id)
    if listen_ref is None or listen_target is None:
        await UniMessage.text("链接码对应的会话已失效").finish(reply_to=True)

    target_ref = await persist_session_reference(session)
    target = to_target(session)
    await create_pipe(listen_ref, target_ref)
    msg = f"管道创建成功:\n{display_pipe(listen_target, target)}"
    await UniMessage.text(msg).finish(reply_to=True)


@pipe_cmd.assign("remove")
async def assign_remove(session: Uninfo, idx: int) -> None:
    ref = await persist_session_reference(session)
    listen_pipes, target_pipes = await get_linked_pipes(ref.scene_persist_id)
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
