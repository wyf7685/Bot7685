from typing import NoReturn

from nonebot import require
from nonebot.plugin import PluginMetadata, inherit_supported_adapters

require("nonebot_plugin_alconna")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_localstore")
require("nonebot_plugin_user")
require("nonebot_plugin_waiter")
require("src.service.cache")
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    Option,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.builtins.extensions.telegram import TelegramSlashExtension
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_waiter.unimsg import prompt, suggest

from .todo_list import SelectedTodo, UserTodo

__plugin_meta__ = PluginMetadata(
    name="todo_list",
    description="待办事项",
    usage="todo --help",
    type="application",
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_user",
        "nonebot_plugin_waiter",
    ),
)

todo_alc = Alconna(
    "todo",
    Subcommand(
        "add",
        Args["content?#todo内容", str],
        Option("-p|--pin"),
        help_text="添加 todo",
    ),
    Subcommand(
        "remove",
        Args["index#todo序号", int],
        alias={"rm", "del"},
        help_text="删除 todo",
    ),
    Subcommand("get", Args["index#todo序号", int], help_text="获取 todo 文本"),
    Subcommand("set", Args["index#todo序号", int], help_text="修改 todo"),
    Subcommand("check", Args["index#todo序号", int], help_text="标记 todo 为已完成"),
    Subcommand("uncheck", Args["index#todo序号", int], help_text="标记 todo 为未完成"),
    Subcommand("pin", Args["index#todo序号", int], help_text="置顶 todo"),
    Subcommand("unpin", Args["index#todo序号", int], help_text="取消 todo"),
    Subcommand("clear", help_text="清空已完成的 todo"),
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
async def handle_todo_add(user_todo: UserTodo, content: Match[str]) -> None:
    if content.available:
        text = content.result
    else:
        res = await prompt("请发送 todo 内容")
        if res is None:
            await UniMessage("todo 发送超时!").finish(reply_to=True)
        text = res.extract_plain_text()

    user_todo.add(text)


@todo.assign("add.pin")
async def handle_todo_add_pin(user_todo: UserTodo) -> None:
    if todo := user_todo.current:
        todo.pinned = True
        await user_todo.save()


@todo.assign("remove")
async def handle_todo_remove(user_todo: UserTodo, index: int) -> None:
    await user_todo.check_index(index)
    user_todo.remove(index)


@todo.assign("get")
async def handle_todo_get(todo: SelectedTodo) -> None:
    await UniMessage.text(todo.content).finish()


@todo.assign("set")
async def handle_todo_set(user_todo: UserTodo, todo: SelectedTodo) -> None:
    await UniMessage.text(f"当前选中的 todo:\n{todo.content}").send()

    text = await prompt("请输入新的 todo 内容")
    if text is None:
        await UniMessage("todo 发送超时!").finish(reply_to=True)
    todo.content = text.extract_plain_text()

    await user_todo.save()
    await UniMessage.text(f"已修改 todo:\n{todo.content}").finish()


@todo.assign("check")
async def handle_todo_check(todo: SelectedTodo) -> None:
    todo.checked = True


@todo.assign("uncheck")
async def handle_todo_uncheck(todo: SelectedTodo) -> None:
    todo.checked = False


@todo.assign("pin")
async def handle_todo_pin(todo: SelectedTodo) -> None:
    todo.pinned = True


@todo.assign("unpin")
async def handle_todo_unpin(todo: SelectedTodo) -> None:
    todo.pinned = False


@todo.assign("clear")
async def handle_todo_clear(user_todo: UserTodo) -> None:
    if not (checked := user_todo.checked()):
        await UniMessage("当前没有已完成的待办事项").finish()

    prompt = (
        UniMessage.text("将要删除的待办事项:\n")
        .image(raw=await user_todo.render(checked))
        .text("\n确认删除? [y|N]")
    )
    resp = await suggest(prompt, ["y", "n"], timeout=30, retry=3)

    if resp is None:
        await UniMessage("删除确认超时，已取消").finish()

    if resp.extract_plain_text().strip().lower() == "y":
        user_todo.clear_checked()


@todo.handle()
async def send_todo_list(user_todo: UserTodo) -> NoReturn:
    await user_todo.save()
    await (
        UniMessage.image(raw=await user_todo.render())
        if user_todo.todo
        else UniMessage.text("🎉当前没有待办事项")
    ).finish(reply_to=True)
