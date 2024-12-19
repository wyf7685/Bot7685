from typing import NoReturn

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_session")
require("nonebot_plugin_waiter")
from nonebot_plugin_alconna import (
    Alconna,
    AlconnaMatcher,
    Args,
    CommandMeta,
    Match,
    Option,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_waiter import prompt, suggest

from .todo_list import UserTodo

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
todo_alc = Alconna(
    "todo",
    Subcommand(
        "add",
        Args["content?#todo内容", str],
        Option("-p|--pin"),
        help_text="添加 todo",
    ),
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

todo = on_alconna(
    todo_alc,
    use_cmd_start=True,
    extensions=[TelegramSlashExtension()],
)


@todo.assign("add")
async def handle_todo_add_args(
    matcher: AlconnaMatcher, content: Match[str], pin: Match
) -> None:
    if content.available:
        matcher.set_path_arg("~content", content.result)
    matcher.set_path_arg("~pin", pin.available)


@todo.assign("add")
@todo.got_path("add.content", prompt="请发送 todo 内容")
async def handle_todo_add(
    matcher: AlconnaMatcher, user_todo: UserTodo, content: str
) -> None:
    pin = matcher.get_path_arg("add.pin", default=False)
    await user_todo.add(content, pin=pin)


@todo.assign("remove")
async def handle_todo_remove(user_todo: UserTodo, index: int) -> NoReturn:
    await user_todo.remove(index)


@todo.assign("get")
async def handle_todo_get(user_todo: UserTodo, index: int) -> NoReturn:
    todo = await user_todo.get(index)
    await UniMessage.text(todo.content).finish()


@todo.assign("set")
async def handle_todo_set(user_todo: UserTodo, index: int) -> NoReturn:
    todo = await user_todo.get(index)
    await UniMessage.text(f"当前选中的 todo:\n{todo.content}").send()
    text = await prompt("请输入新的 todo 内容")
    if text is None:
        await UniMessage("todo 发送超时!").finish(reply_to=True)
    todo.content = text.extract_plain_text()
    await user_todo.save()
    await UniMessage.text(f"已修改 todo:\n{todo.content}").finish()


@todo.assign("check")
async def handle_todo_check(user_todo: UserTodo, index: int) -> NoReturn:
    await user_todo.check(index)


@todo.assign("uncheck")
async def handle_todo_uncheck(user_todo: UserTodo, index: int) -> NoReturn:
    await user_todo.uncheck(index)


@todo.assign("pin")
async def handle_todo_pin(user_todo: UserTodo, index: int) -> NoReturn:
    await user_todo.pin(index)


@todo.assign("unpin")
async def handle_todo_unpin(user_todo: UserTodo, index: int) -> NoReturn:
    await user_todo.unpin(index)


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


@todo.handle()
async def send_todo_list(user_todo: UserTodo) -> NoReturn:
    await (
        UniMessage.image(raw=await user_todo.render())
        if user_todo.todo
        else UniMessage.text("🎉当前没有待办事项")
    ).finish(reply_to=True)
