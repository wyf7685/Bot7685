import json
import re
from json import JSONDecodeError
from typing import Any, Optional

from nonebot import require
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.adapters.onebot.v11.permission import GROUP
from nonebot.adapters.onebot.v11.utils import unescape
from nonebot.log import logger
from nonebot.matcher import Matcher
from nonebot.params import ArgPlainText, RegexDict
from nonebot.permission import SUPERUSER, Permission
from nonebot.plugin import PluginMetadata, on_regex
from nonebot.rule import Rule

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna.uniseg import UniMessage

from .config import APIKeyPool, Config, plugin_config
from .depends import ALLOW_PRIVATE, IS_ADMIN, AdminCheck, AuthCheck, GroupId, MsgAt
from .exceptions import NeedCreateSession
from .preset import presets_str
from .session import Session, session_container

customize_prefix = plugin_config.customize_prefix
customize_talk_cmd = plugin_config.customize_talk_cmd
# 因为电脑端的qq在输入/chat xxx时候经常被转换成表情，所以支持自定义指令前缀替换"chat"
change_chat_to = plugin_config.change_chat_to
prefix_str = customize_prefix if customize_prefix is not None else "/"
chat_str = f"(chat|{change_chat_to})" if change_chat_to else "chat"
talk_cmd_str = customize_talk_cmd if customize_talk_cmd else "talk"
pattern_str = prefix_str + chat_str
menu_chat_str = prefix_str + (f"{change_chat_to}" if change_chat_to else "chat")

__usage__: str = (
    "指令表：\n"
    f"    {menu_chat_str} help 获取指令帮助菜单\n"
    f"    {menu_chat_str} auth 获取当前群会话管理权限状态\n"
    f"    {menu_chat_str} auth on 设置当前群仅管理员可以管理会话\n"
    f"    {menu_chat_str} auth off 设置当前群所有人均可管理会话\n"
    f"    {prefix_str}{talk_cmd_str} <会话内容> 在当前会话中进行会话(同样不需要括号，后面直接接你要说的话就行)\n"
    ">> 增\n"
    f"    {menu_chat_str} new  根据预制模板prompt创建并加入一个新的会话\n"
    f"    {menu_chat_str} new <自定义prompt> 根据自定义prompt创建并加入一个新的会话\n"
    f"    {menu_chat_str} json 根据历史会话json来创建一个会话，输入该命令后会提示你在下一个消息中输入json\n"
    f"    {menu_chat_str} cp 根据当前会话创建并加入一个新的会话\n"
    f"    {menu_chat_str} cp <id> 根据会话<id>为模板进行复制新建加入（id为{menu_chat_str} list中的序号）\n"
    ">> 删\n"
    f"    {menu_chat_str} del 删除当前所在会话\n"
    f"    {menu_chat_str} del <id> 删除序号为<id>的会话（id为{menu_chat_str} list中的序号）\n"
    f"    {menu_chat_str} clear 清空本群全部会话\n"
    f"    {menu_chat_str} clear <@user> 删除@用户创建的会话\n"
    ">> 改\n"
    f"    {menu_chat_str} join <id> 加入会话（id为{menu_chat_str} list中的序号）\n"
    f"    {menu_chat_str} rename <name> 重命名当前会话\n"
    ">> 查\n"
    f"    {menu_chat_str} who 查看当前会话信息\n"
    f"    {menu_chat_str} list 获取当前群所有存在的会话的序号及创建时间\n"
    f"    {menu_chat_str} list <@user> 获取当前群查看@的用户创建的会话\n"
    f"    {menu_chat_str} prompt 查看当前会话的prompt\n"
    f"    {menu_chat_str} dump 导出当前会话json字符串格式的上下文信息，可以用于{menu_chat_str} json导入\n"
    f"    {menu_chat_str} keys 脱敏显示当前失效api key，仅主人"
)
__plugin_meta__ = PluginMetadata(
    name="多功能ChatGPT插件",
    description="基于chatGPT-3.5-turbo API的nonebot插件",
    usage=__usage__,
    config=Config,
    extra={
        "License": "BSD License",
        "Author": "颜曦",
        "version": "1.6.1",
    },
)

api_keys: APIKeyPool = session_container.api_keys
base_url: str = session_container.base_url
temperature: float = plugin_config.temperature
model: str = plugin_config.gpt_model_name
max_tokens: int = plugin_config.max_tokens
auto_create_preset_info: bool = plugin_config.auto_create_preset_info
at_sender: bool = plugin_config.at_sender


def on(
    pattern: str,
    permission: Permission = ALLOW_PRIVATE,
    rule: Optional[Rule] = None,
    prefix: str = rf"^{pattern_str}\s+",
    flags: re.RegexFlag | int = 0,
):
    return on_regex(prefix + pattern, flags, rule=rule, permission=permission)


Chat = on_regex(rf"^{prefix_str}{talk_cmd_str}\s+(?P<content>.+)", flags=re.S)  # 聊天
CallMenu = on(r"help$")  # 呼出菜单
ShowList = on(r"list\s*$")  # 展示群聊天列表
Join = on(r"join\s+(?P<id>\d+)")  # 加入会话
Delete = on(r"del\s+(?P<id>\d+)")  # 删除会话
DelSelf = on(r"del\s*$")  # 删除当前会话
Dump = on(r"dump$")  # 导出json
CreateConversationWithPrompt = on(r"new\s+(?P<prompt>.+)$", flags=re.S)
CreateConversationWithTemplate = on(r"new$")  # 利用模板创建会话
CreateConversationWithJson = on(r"json$")  # 利用json创建会话
ChatCopy = on(r"cp\s+(?P<id>\d+)$")
ChatCP = on(r"cp$")
ChatWho = on(r"who$")
ChatUserList = on(r"list\s*\S+$")  # 展示群聊天列表
ReName = on(r"rename\s+(?P<name>.+)$")  # 重命名当前会话
ChatPrompt = on(r"prompt$")
ChatClear = on(rf"{pattern_str}\s+clear$", rule=IS_ADMIN)
ChatClearAt = on(rf"{pattern_str}\s+clear\s*\S+$")
SetAuthOn = on(r"auth on$", GROUP, IS_ADMIN)
SetAuthOff = on(r"auth off$", GROUP, IS_ADMIN)
ShowAuth = on(r"auth$", GROUP)
ShowFailKey = on(r"keys$", SUPERUSER)


@ShowFailKey.handle()
async def _():
    await UniMessage(api_keys.show_fail_keys()).finish(at_sender=True)


@ShowAuth.handle()
async def _(group_id: GroupId):
    perm = "仅有管理员" if session_container.get_group_auth(group_id) else "所有人均"
    await UniMessage(f"当前{perm}有权限管理会话").finish(at_sender=True)


@SetAuthOff.handle()
async def _(group_id: GroupId):
    session_container.set_group_auth(group_id, False)
    await UniMessage("设置成功，当前所有人均有权限管理会话").finish(at_sender=True)


@SetAuthOn.handle()
async def _(group_id: GroupId):
    session_container.set_group_auth(group_id, True)
    await UniMessage("设置成功，当前仅有管理员有权限管理会话").finish(at_sender=True)


@ChatClear.handle()
async def _(group_id: GroupId):
    session_list: list[Session] = session_container.get_group_sessions(group_id)
    num = len(session_list)
    for session in session_list:
        await session_container.delete_session(session, group_id)
    await UniMessage(f"成功删除全部共{num}条会话").finish(at_sender=True)


@ChatClearAt.handle()
async def _(
    event: GroupMessageEvent,
    user_id: MsgAt,
    group_id: GroupId,
    is_admin: AdminCheck,
):
    if user_id != event.user_id and not is_admin:
        await UniMessage("您不是该会话的创建者或管理员!").finish(at_sender=True)
    session_list: list[Session] = [
        s
        for s in session_container.sessions
        if s.group == group_id and s.creator == user_id
    ]
    if not session_list:
        msg = UniMessage(f"本群用户 {user_id} 还没有创建过会话哦")
        await msg.finish(at_sender=True)
    for session in session_list:
        await session_container.delete_session(session, group_id)
    text = f"成功删除本群用户 {user_id} 创建的全部会话共{len(session_list)}条"
    await UniMessage(text).finish(at_sender=True)


@ChatCP.handle(parameterless=[AuthCheck])
async def _(event: MessageEvent, group_id: GroupId):
    user_id = event.user_id
    group_usage = session_container.get_group_usage(group_id)
    if user_id not in group_usage:
        text = f"请先加入一个会话，再进行复制当前会话 或者使用 {menu_chat_str} cp <id> 进行复制"
        await UniMessage(text).finish(at_sender=True)
    session = group_usage[user_id]
    group_usage[user_id].del_user(user_id)
    new_session = session_container.create_with_session(session, user_id, group_id)

    text = f"创建并加入会话 '{new_session.name}' 成功!"
    await UniMessage(text).finish(at_sender=True)


@ChatPrompt.handle()
async def _(event: MessageEvent, group_id: GroupId):
    group_usage = session_container.get_group_usage(group_id)
    if event.user_id not in group_usage:
        text = "请先加入一个会话，再进行重命名"
    else:
        session = group_usage[event.user_id]
        text = f"会话：{session.name}\nprompt：{session.prompt}"
    await UniMessage(text).finish(at_sender=True)


@ReName.handle(parameterless=[AuthCheck])
async def _(
    event: MessageEvent,
    group_id: GroupId,
    is_admin: AdminCheck,
    info: dict[str, Any] = RegexDict(),
):
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)
    if event.user_id not in group_usage:
        await UniMessage("请先加入一个会话，再进行重命名").finish(at_sender=True)
    session = group_usage[event.user_id]
    name = unescape(info.get("name", "").strip())
    if session.creator == event.user_id or is_admin:
        session.rename(name[:32])
        await UniMessage(f"当前会话已命名为 {session.name}").finish(at_sender=True)
    logger.info(f"重命名群 {group_id} 会话 {session.name} 失败：权限不足")
    await UniMessage("您不是该会话的创建者或管理员!").finish(at_sender=True)


@ChatUserList.handle()
async def _(user_id: MsgAt, group_id: GroupId):
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


@ChatWho.handle()
async def _(event: MessageEvent, group_id: GroupId):
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)
    if event.user_id not in group_usage:
        text = "当前没有加入任何会话，请加入或创建一个会话"
        await UniMessage(text).finish(at_sender=True)

    session = group_usage[event.user_id]
    await UniMessage(
        f"当前所在会话信息:\n"
        f"名称: {session.name[:10]}\n"
        f"创建者: {session.creator}\n"
        f"时间: {session.creation_datetime}\n"
        f"可以使用 {menu_chat_str} dump 导出json字符串格式的上下文信息"
    ).finish(at_sender=True)


@ChatCopy.handle(parameterless=[AuthCheck])
async def _(
    event: MessageEvent,
    group_id: GroupId,
    info: dict[str, Any] = RegexDict(),
):
    session_id = int(info.get("id", "").strip())
    user_id: int = event.user_id
    group_sessions: list[Session] = session_container.get_group_sessions(group_id)
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)

    if not group_sessions:
        text = f"本群尚未创建过会话!请用{menu_chat_str} new命令来创建会话!"
        await UniMessage(text).finish(at_sender=True)
    if session_id < 1 or session_id > len(group_sessions):
        await UniMessage("序号超出!").finish(at_sender=True)

    session = group_sessions[session_id - 1]
    if user_id in group_usage:
        group_usage[user_id].del_user(user_id)
    new_session = session_container.create_with_session(session, user_id, group_id)
    text = f"创建并加入会话 '{new_session.name}' 成功!"
    await UniMessage(text).finish(at_sender=True)


@Dump.handle()
async def _(event: MessageEvent, group_id: GroupId):
    user_id: int = int(event.get_user_id())
    try:
        session: Session = session_container.get_user_usage(group_id, user_id)
        await UniMessage(session.dump2json_str()).finish(at_sender=True)
    except NeedCreateSession:
        await UniMessage("请先加入一个会话").finish(at_sender=True)


@Chat.handle()
async def _(
    event: MessageEvent,
    group_id: GroupId,
    info: dict[str, Any] = RegexDict(),
):
    content = unescape(info.get("content", "").strip())
    if not content:
        await UniMessage("输入不能为空!").finish(at_sender=True)
    user_id = event.user_id
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)
    if user_id not in group_usage:  # 若用户没有加入任何会话则先创建会话
        session = session_container.create_with_template("1", user_id, group_id)
        logger.info(f"{user_id} 自动创建并加入会话 '{session.name}'")
        if auto_create_preset_info:
            text = f"自动创建并加入会话 '{session.name}' 成功"
            await UniMessage(text).send(at_sender=True)
    else:
        session = group_usage[user_id]
    answer = await session.ask_with_content(
        api_keys, base_url, content, "user", temperature, model, max_tokens
    )
    await UniMessage(answer).finish(at_sender=at_sender)


@Join.handle()
async def _(
    event: MessageEvent,
    group_id: GroupId,
    info: dict[str, Any] = RegexDict(),
):
    session_id: int = int(info.get("id", "").strip())
    group_sessions: list[Session] = session_container.get_group_sessions(group_id)
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)
    if not group_sessions:
        text = f"本群尚未创建过会话!请用{menu_chat_str} new命令来创建会话!"
        await UniMessage(text).finish(at_sender=True)
    if session_id < 1 or session_id > len(group_sessions):
        await UniMessage("序号超出!").finish(at_sender=True)

    user_id = event.user_id
    session: Session = group_sessions[session_id - 1]
    if user_id in group_usage:
        group_usage[user_id].del_user(user_id)
    session.add_user(user_id)
    group_usage[user_id] = session

    text = f"加入会话 {session_id}:{session.name} 成功!"
    await UniMessage(text).finish(at_sender=True)


@CallMenu.handle()
async def _():
    await CallMenu.finish(__usage__, at_sender=True)


@DelSelf.handle(parameterless=[AuthCheck])
async def _(event: MessageEvent, group_id: GroupId, is_admin: AdminCheck):
    user_id: int = int(event.get_user_id())
    group_usage: dict[int, Session] = session_container.get_group_usage(group_id)
    session = group_usage.pop(user_id, None)
    if not session:
        await UniMessage("当前不存在会话").finish(at_sender=True)
    if session.creator == user_id or is_admin:
        await session_container.delete_session(session, group_id)
        await UniMessage("删除成功!").finish(at_sender=True)
    logger.info(f"删除群 {group_id} 会话 {session.name} 失败：权限不足", at_sender=True)
    await UniMessage("您不是该会话的创建者或管理员!").finish(at_sender=True)


@Delete.handle(parameterless=[AuthCheck])
async def _(
    event: MessageEvent,
    group_id: GroupId,
    is_admin: AdminCheck,
    info: dict[str, Any] = RegexDict(),
):
    session_id = int(info.get("id", "").strip())
    user_id: int = int(event.get_user_id())
    group_sessions: list[Session] = session_container.get_group_sessions(group_id)
    if not group_sessions:
        await UniMessage("当前不存在会话").finish(at_sender=True)
    if session_id < 1 or session_id > len(group_sessions):
        await UniMessage("序号超出!").finish(at_sender=True)
    session: Session = group_sessions[session_id - 1]
    if session.creator == user_id or is_admin:
        await session_container.delete_session(session, group_id)
        await UniMessage("删除成功!").finish(at_sender=True)
    else:
        logger.info(
            f"删除群 {group_id} 会话 {session.name} 失败：权限不足",
            at_sender=True,
        )
        await UniMessage("您不是该会话的创建者或管理员!").finish(at_sender=True)


@ShowList.handle()
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


@CreateConversationWithPrompt.handle(parameterless=[AuthCheck])
async def _(
    event: MessageEvent,
    group_id: GroupId,
    info: dict[str, Any] = RegexDict(),
):
    custom_prompt: str = unescape(info.get("prompt", "").strip())
    session = session_container.create_with_str(
        custom_prompt, event.user_id, group_id, custom_prompt[:5]
    )
    await UniMessage(f"成功创建并加入会话 '{session.name}' ").finish(at_sender=True)


@CreateConversationWithTemplate.got(
    key="template",
    prompt=presets_str,
    parameterless=[AuthCheck],
)
async def _(
    matcher: Matcher,
    event: MessageEvent,
    group_id: GroupId,
    template_id: str = ArgPlainText("template"),
):
    user_id: int = int(event.get_user_id())
    if not template_id.isdigit():
        await matcher.reject("输入ID无效！", at_sender=True)
    session = session_container.create_with_template(template_id, user_id, group_id)
    await matcher.send(
        f"使用模板 '{template_id}' 创建并加入会话 '{session.name}' 成功!",
        at_sender=True,
    )


@CreateConversationWithJson.got(
    key="jsonStr",
    prompt="请直接输入json",
    parameterless=[AuthCheck],
)
async def _(
    event: MessageEvent,
    group_id: GroupId,
    json_str: str = ArgPlainText("jsonStr"),
):
    try:
        chat_log = json.loads(json_str)
    except JSONDecodeError:
        logger.error("json字符串错误!")
        await UniMessage("Json错误！").finish(at_sender=True)

    if not chat_log or not isinstance(chat_log[0], dict) or not chat_log[0].get("role"):
        await UniMessage("Json错误！").finish(at_sender=True)

    session: Session = session_container.create_with_chat_log(
        chat_log,
        event.user_id,
        group_id,
        name=chat_log[0].get("content", "")[:5],
    )
    await UniMessage(f"创建并加入会话 '{session}' 成功!").send(at_sender=True)
