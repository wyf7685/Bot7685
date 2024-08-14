from typing import Literal

from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot_plugin_alconna import Alconna, Args, At, Match, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

from .depends import IS_ADMIN, AtTarget, AuthCheck, GroupId
from .session import Session, session_container

__usage__ = ""


chat = on_alconna(
    Alconna(
        "chat",
        Subcommand("help"),
        Subcommand("new", Args["prompt?", str]),
        Subcommand("json"),
        Subcommand("cp", Args["id?", int]),
        Subcommand("del", Args["id?", int]),
        Subcommand("clear", Args["target?", At]),
        Subcommand("join", Args["id", int]),
        Subcommand("rename", Args["name", str]),
        Subcommand("who"),
        Subcommand("list", Args["target?", At]),
        Subcommand("prompt"),
        Subcommand("dump"),
    )
)

chat_admin = on_alconna(
    Alconna("chat", Subcommand("clear", Args["target?", At])),
    rule=IS_ADMIN,
)

chat_group_admin = on_alconna(
    Alconna("chat", Subcommand("auth", Args["op?", Literal["on", "off"]])),
    permission=GROUP,
    rule=IS_ADMIN,
)

chat_superuser = on_alconna(Alconna("chat", Subcommand("keys")))


@chat.assign("help")
async def _():
    await UniMessage(__usage__).send(at_sender=True)


chat_new = chat.dispatch("new")


@chat_new.handle(parameterless=[AuthCheck])
async def _(event: MessageEvent, group_id: GroupId, prompt: Match[str]):
    if prompt.available:
        custom_prompt = prompt.result
        session = session_container.create_with_str(
            custom_prompt,
            event.user_id,
            group_id,
            custom_prompt[:5],
        )
        await UniMessage(f"成功创建并加入会话 '{session.name}' ").finish(at_sender=True)


@chat.assign("list.target")
async def _(user_id: AtTarget, group_id: GroupId):
    session_list: list[Session] = [
        s
        for s in session_container.sessions
        if s.group == group_id and s.creator == user_id
    ]
    msg = UniMessage.at(str(user_id)).text(f" 在群中创建会话{len(session_list)}条: \n")
    for session in session_list:
        msg.text(
            f" 名称: {session.name[:10]} "
            f"创建者: {session.creator} "
            f"时间: {session.creation_datetime}\n"
        )
    await msg.finish(at_sender=True)


@chat.assign("list")
async def _(group_id: GroupId):
    session_list: list[Session] = session_container.get_group_sessions(group_id)
    msg: str = f"本群全部会话共{len(session_list)}条：\n"
    for index, session in enumerate(session_list, 1):
        msg += (
            f"{index}. {session.name} "
            f"创建者: {session.creator} "
            f"时间: {session.creation_datetime}\n"
        )
    await UniMessage(msg).finish(at_sender=True)
