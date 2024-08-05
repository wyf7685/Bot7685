from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
require("nonebot_plugin_session")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Match,
    Subcommand,
    UniMessage,
    on_alconna,
)

from .todo_list import UserTodo, TodoList

todo = on_alconna(
    Alconna(
        "todo",
        Subcommand("show"),
        Subcommand("add", Args["content", str]),
        Subcommand("remove", Args["index", int]),
        Subcommand("check", Args["index", int]),
        Subcommand("uncheck", Args["index", int]),
        Subcommand("pin", Args["index", int]),
        Subcommand("unpin", Args["index", int]),
    )
)


async def send_todo(user_todo: TodoList):
    if user_todo.todo:
        await UniMessage("==== TODO List ====\n").text(user_todo.show()).send()
    else:
        await UniMessage("🎉当前没有待办事项").send()


@todo.assign("show")
async def handle_todo_show(user_todo: UserTodo):
    await send_todo(user_todo)


@todo.assign("add")
async def handle_todo_add(user_todo: UserTodo, content: Match[str]):
    user_todo.add(content.result)
    await send_todo(user_todo)


@todo.assign("remove")
async def handle_todo_remove(user_todo: UserTodo, index: Match[int]):
    user_todo.remove(index.result)
    await send_todo(user_todo)


@todo.assign("check")
async def handle_todo_check(user_todo: UserTodo, index: Match[int]):
    user_todo.check(index.result)
    await send_todo(user_todo)


@todo.assign("uncheck")
async def handle_todo_uncheck(user_todo: UserTodo, index: Match[int]):
    user_todo.uncheck(index.result)
    await send_todo(user_todo)


@todo.assign("pin")
async def handle_todo_pin(user_todo: UserTodo, index: Match[int]):
    user_todo.pin(index.result)
    await send_todo(user_todo)


@todo.assign("unpin")
async def handle_todo_unpin(user_todo: UserTodo, index: Match[int]):
    user_todo.unpin(index.result)
    await send_todo(user_todo)
