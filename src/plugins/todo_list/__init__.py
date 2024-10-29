from typing import NoReturn

from nonebot import require
from nonebot.params import Depends
from nonebot.plugin import PluginMetadata, inherit_supported_adapters
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_session")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    Option,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_waiter import prompt, suggest

from .todo_list import Todo, TodoList, UserTodo

__plugin_meta__ = PluginMetadata(
    name="todo_list",
    description="待办事项",
    usage="todo --help",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_htmlrender",
        "nonebot_plugin_localstore",
        "nonebot_plugin_session",
        "nonebot_plugin_waiter",
    ),
)

arg_index = Args["index#todo序号", int]
arg_content = Args["content?#todo内容", str]
opt_pin = Option("-p|--pin")
alc = Alconna(
    "todo",
    Subcommand("list", alias={"ls", "show"}, help_text="显示 todo"),
    Subcommand("add", arg_content, opt_pin, help_text="添加 todo"),
    Subcommand("remove", arg_index, alias={"rm", "del"}, help_text="删除 todo"),
    Subcommand("get", arg_index, help_text="获取 todo 文本"),
    Subcommand("set", arg_index, help_text="修改 todo"),
    Subcommand("check", arg_index, help_text="标记 todo 为已完成"),
    Subcommand("uncheck", arg_index, help_text="标记 todo 为未完成"),
    Subcommand("pin", arg_index, help_text="置顶 todo"),
    Subcommand("unpin", arg_index, help_text="取消 todo"),
    Subcommand("purge", help_text="清空已完成的 todo"),
    meta=CommandMeta(
        description="待办事项",
        usage="todo --help",
        author="wyf7685",
    ),
)
todo = on_alconna(alc, use_cmd_start=True)


async def send_todo(user_todo: TodoList) -> NoReturn:
    msg = (
        UniMessage.image(raw=await user_todo.render())
        if user_todo.todo
        else UniMessage.text("🎉当前没有待办事项")
    )
    await msg.finish(reply_to=True)


@todo.assign("list")
async def handle_todo_list(user_todo: UserTodo) -> NoReturn:
    await send_todo(user_todo)


async def _todo_add_content(content: Match[str], state: T_State) -> None:
    if content.available:
        state["content"] = content.result
        return

    text = await prompt("请发送 todo 内容", timeout=120)
    if text is None:
        await UniMessage("todo 发送超时!").finish(reply_to=True)
    state["content"] = text.extract_plain_text().strip()


@todo.assign("add", parameterless=[Depends(_todo_add_content)])
async def handle_todo_add(user_todo: UserTodo, state: T_State) -> None:
    state["todo"] = await user_todo.add(state["content"])


@todo.assign("add.pin")
async def handle_todo_add_pin(user_todo: UserTodo, state: T_State) -> None:
    todo: Todo = state["todo"]
    todo.pinned = True
    await user_todo.save()


@todo.assign("add")
async def handle_todo_add_send(user_todo: UserTodo) -> NoReturn:
    await send_todo(user_todo)


@todo.assign("remove")
async def handle_todo_remove(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    await user_todo.remove(index.result)
    await send_todo(user_todo)


@todo.assign("get")
async def handle_todo_get(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    todo = await user_todo.get(index.result)
    await UniMessage.text(todo.content).finish()


@todo.assign("set")
async def handle_todo_set(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    todo = await user_todo.get(index.result)
    await UniMessage.text(f"当前选中的 todo:\n{todo.content}").send()
    text = await prompt("请输入新的 todo 内容")
    if text is None:
        await UniMessage("todo 发送超时!").finish(reply_to=True)
    todo.content = text.extract_plain_text()
    await user_todo.save()
    await UniMessage.text(f"已修改 todo:\n{todo.content}").finish()


@todo.assign("check")
async def handle_todo_check(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    await user_todo.check(index.result)
    await send_todo(user_todo)


@todo.assign("uncheck")
async def handle_todo_uncheck(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    await user_todo.uncheck(index.result)
    await send_todo(user_todo)


@todo.assign("pin")
async def handle_todo_pin(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    await user_todo.pin(index.result)
    await send_todo(user_todo)


@todo.assign("unpin")
async def handle_todo_unpin(user_todo: UserTodo, index: Match[int]) -> NoReturn:
    await user_todo.unpin(index.result)
    await send_todo(user_todo)


@todo.assign("purge")
async def handle_todo_purge(user_todo: UserTodo) -> NoReturn:
    prompt = await (
        UniMessage.text("将要删除的待办事项:\n")
        .image(raw=await user_todo.render(user_todo.checked()))
        .text("\n确认删除? [y|N]")
    ).export()
    resp = await suggest(prompt, ["y", "n"], timeout=30, retry=3)

    if resp is None:
        await UniMessage("删除确认超时，已取消").finish()

    if resp.extract_plain_text().strip().lower() == "y":
        await user_todo.purge()

    await send_todo(user_todo)
