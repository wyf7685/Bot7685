from nonebot.adapters import Bot
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    CommandMeta,
    Option,
    Subcommand,
    on_alconna,
)

from .trust_data import TrustData, set_trusted

alc = Alconna(
    "trust",
    Subcommand(
        "add",
        Subcommand("user", Args["user", At | str], help_text="添加可信用户"),
        Subcommand("group", Args["group", str], help_text="添加可信群组"),
        help_text="添加可信用户或群组",
    ),
    Subcommand(
        "remove",
        Subcommand("user", Args["user", At | str], help_text="移除可信用户"),
        Subcommand("group", Args["group", str], help_text="移除可信群组"),
        help_text="移除可信用户或群组",
        alias={"rm"},
    ),
    Subcommand(
        "list",
        Option("--user|-u", help_text="列出可信用户"),
        Option("--group|-g", help_text="列出可信群组"),
        help_text="列出可信用户或群组",
        alias={"ls"},
    ),
    Subcommand("refresh", help_text="从文件重载数据"),
    meta=CommandMeta(
        description="管理可信用户或群组",
        usage="trust -h",
        example="trust add user @xxx",
    ),
)
matcher = on_alconna(alc, permission=SUPERUSER)


@matcher.assign("add.user")
async def add_user(user: At | str) -> None:
    user = user.target if isinstance(user, At) else user
    set_trusted("add", "user", user)
    await matcher.send(f"成功添加可信用户 {user}")


@matcher.assign("add.group")
async def add_group(group: str) -> None:
    set_trusted("add", "group", group)
    await matcher.send(f"成功添加可信群组 {group}")


@matcher.assign("remove.user")
async def remove_user(user: At | str) -> None:
    user = user.target if isinstance(user, At) else user
    set_trusted("remove", "user", user)
    await matcher.send(f"成功移除可信用户 {user}")


@matcher.assign("remove.group")
async def remove_group(group: str) -> None:
    set_trusted("remove", "group", group)
    await matcher.send(f"成功移除可信群组 {group}")


@matcher.assign("list.user")
async def list_user(bot: Bot) -> None:
    users = [
        user.partition(":")[2]
        for user in TrustData.load(use_cache=False).user
        if user.startswith(bot.type)
    ]
    await matcher.send(("可信用户\n" + "\n".join(users)) if users else "没有可信用户")


@matcher.assign("list.group")
async def list_group(bot: Bot) -> None:
    groups = [
        group.partition(":")[2]
        for group in TrustData.load(use_cache=False).group
        if group.startswith(bot.type)
    ]
    await matcher.send(("可信群组\n" + "\n".join(groups)) if groups else "没有可信群组")


@matcher.assign("refresh")
async def refresh() -> None:
    TrustData.load(use_cache=False)
    await matcher.send("已从文件重载数据")
