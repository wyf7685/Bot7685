from nonebot import require
from nonebot.params import Depends
from nonebot.typing import T_State

require("nonebot_plugin_alconna")
require("nonebot_plugin_datastore")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_session")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import Alconna, Args, Match, Option, Subcommand, on_alconna
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_waiter import prompt, suggest

from .todo_list import Todo, TodoList, UserTodo

todo = on_alconna(
    Alconna(
        "todo",
        Subcommand("show", alias=["list"]),
        Subcommand("add", Args["content?", str], Option("-p|--pin")),
        Subcommand("remove", Args["index", int], alias={"del"}),
        Subcommand("check", Args["index", int]),
        Subcommand("uncheck", Args["index", int]),
        Subcommand("pin", Args["index", int]),
        Subcommand("unpin", Args["index", int]),
        Subcommand("purge"),
    ),
)

todo_add = todo.dispatch("add")


async def send_todo(user_todo: TodoList):
    msg = (
        UniMessage.image(raw=await user_todo.render())
        if user_todo.todo
        else UniMessage.text("🎉当前没有待办事项")
    )
    await msg.finish(reply_to=True)


@todo.assign("show")
async def handle_todo_show(user_todo: UserTodo):
    await send_todo(user_todo)


async def _todo_add_content(content: Match[str], state: T_State):
    if content.available:
        state["content"] = content.result
        return

    text = await prompt("请发送 todo 内容", timeout=120)
    if text is None:
        await UniMessage("todo 发送超时!").finish(reply_to=True)
    state["content"] = text.extract_plain_text().strip()


@todo_add.assign("~", parameterless=[Depends(_todo_add_content)])
async def handle_todo_add(user_todo: UserTodo, state: T_State):
    state["todo"] = await user_todo.add(state["content"])


@todo_add.assign("~pin")
async def handle_todo_add_pin(user_todo: UserTodo, state: T_State):
    todo: Todo = state["todo"]
    todo.pinned = True
    await user_todo.save()


@todo_add.assign("~")
async def handle_todo_add_send(user_todo: UserTodo):
    await send_todo(user_todo)


@todo.assign("remove")
async def handle_todo_remove(user_todo: UserTodo, index: Match[int]):
    await user_todo.remove(index.result)
    await send_todo(user_todo)


@todo.assign("check")
async def handle_todo_check(user_todo: UserTodo, index: Match[int]):
    await user_todo.check(index.result)
    await send_todo(user_todo)


@todo.assign("uncheck")
async def handle_todo_uncheck(user_todo: UserTodo, index: Match[int]):
    await user_todo.uncheck(index.result)
    await send_todo(user_todo)


@todo.assign("pin")
async def handle_todo_pin(user_todo: UserTodo, index: Match[int]):
    await user_todo.pin(index.result)
    await send_todo(user_todo)


@todo.assign("unpin")
async def handle_todo_unpin(user_todo: UserTodo, index: Match[int]):
    await user_todo.unpin(index.result)
    await send_todo(user_todo)


@todo.assign("purge")
async def handle_todo_purge(user_todo: UserTodo):
    prompt = "\n".join(
        [
            "将要删除的待办事项:",
            *(todo.show() for todo in user_todo.checked()),
            "\n确认删除? [y|N]",
        ]
    )
    resp = await suggest(prompt, ["y", "n"], timeout=30, retry=3)

    if resp is None:
        await UniMessage("删除确认超时，已取消").finish()

    if resp.extract_plain_text().strip().lower() == "y":
        await user_todo.purge()

    await send_todo(user_todo)
