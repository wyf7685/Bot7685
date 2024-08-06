from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
require("nonebot_plugin_session")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    Match,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_waiter import prompt

from .todo_list import TodoList, UserTodo

todo = on_alconna(
    Alconna(
        "todo",
        Subcommand("show"),
        Subcommand(
            "add",
            Option("-p|--pin", Args["pin", bool], default=False),
            Args["content?", str],
        ),
        Subcommand("remove", Args["index", int]),
        Subcommand("check", Args["index", int]),
        Subcommand("uncheck", Args["index", int]),
        Subcommand("pin", Args["index", int]),
        Subcommand("unpin", Args["index", int]),
    )
)


async def send_todo(user_todo: TodoList):
    msg = (
        f"==== TODO List ====\n{user_todo.show()}"
        if user_todo.todo
        else "🎉当前没有待办事项"
    )
    await UniMessage.text(msg).send()


@todo.assign("show")
async def handle_todo_show(user_todo: UserTodo):
    await send_todo(user_todo)


@todo.assign("add")
async def handle_todo_add(user_todo: UserTodo, pin: Match[bool], content: Match[str]):
    if content.available:
        text = content.result
    else:
        text = await prompt("请发送 todo 内容", timeout=30)
        if text is None:
            await UniMessage("todo 发送超时!").finish(reply_to=True)
        text = text.extract_plain_text().strip()

    todo = user_todo.add(text)
    if pin.result:
        todo.pinned = True
        user_todo.save()
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
