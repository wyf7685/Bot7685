# ruff: noqa

from typing import Literal

import nonebot_plugin_waiter as waiter
from nonebot.adapters import Event
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Args, At, Match, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage

from .depends import IS_ADMIN, AtTarget, AuthCheck, GroupId
from .preset import presets_str
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

chat_superuser = on_alconna(Alconna("chat", Subcommand("keys")), permission=SUPERUSER)


@chat.assign("help")
async def _():
    await UniMessage(__usage__).send(at_sender=True)


@chat.assign("new.prompt", parameterless=[AuthCheck])
async def _(event: Event, group_id: GroupId, prompt: Match[str]):
    session = session_container.create_with_str(
        prompt.result,
        event.get_user_id(),
        group_id,
        prompt.result[:5],
    )
    await UniMessage(f"成功创建并加入会话 '{session.name}' ").finish(at_sender=True)


@chat.assign("new", parameterless=[AuthCheck])
async def _(event: Event, group_id: GroupId):
    msg = await waiter.prompt_until(
        presets_str,
        lambda m: m.extract_plain_text().isdigit(),
        retry=3,
        retry_prompt="输入ID无效，请重新输入！\n剩余次数：{count}",
    )
    if msg is None:
        await UniMessage().finish()

    template_id = msg.extract_plain_text()
    session = session_container.create_with_template(
        template_id,
        event.get_user_id(),
        group_id,
    )
    msg = UniMessage(f"使用模板 '{template_id}' 创建并加入会话 '{session.name}' 成功!")
    await msg.finish(at_sender=True)


@chat.assign("json")
async def _():
    pass


@chat.assign("list.target")
async def _(user_id: AtTarget, group_id: GroupId):
    sessions = [
        session
        for session in session_container.sessions
        if session.group == group_id and session.creator == user_id
    ]
    msg = UniMessage.at(user_id).text(f" 在群中创建会话{len(sessions)}条: \n\n")
    for session in sessions:
        msg = msg.text(
            f"名称: {session.name[:10]}\n"
            f"创建者: {session.creator}\n"
            f"时间: {session.creation_datetime}\n\n"
        )
    await msg.finish(at_sender=True)


@chat.assign("list")
async def _(group_id: GroupId):
    session_list: list[Session] = session_container.get_group_sessions(group_id)
    msg: str = f"本群全部会话共{len(session_list)}条：\n"
    for index, session in enumerate(session_list, 1):
        msg += f"{index}. {session.name} 创建者: {session.creator} 时间: {session.creation_datetime}\n"
    await UniMessage(msg).finish(at_sender=True)
