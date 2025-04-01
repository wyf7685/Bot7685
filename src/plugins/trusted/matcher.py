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

from .trust_data import load_trust_data, set_trusted

matcher = on_alconna(
    Alconna(
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
        meta=CommandMeta(
            description="管理可信用户或群组",
            usage="trust -h",
            example="trust add user @xxx",
        ),
    ),
    permission=SUPERUSER,
    use_cmd_start=True,
)


@matcher.assign("add.user")
async def add_user(user: At | str) -> None:
    set_trusted("add", "user", user.target if isinstance(user, At) else user)


@matcher.assign("add.group")
async def add_group(group: str) -> None:
    set_trusted("add", "group", group)


@matcher.assign("remove.user")
async def remove_user(user: At | str) -> None:
    set_trusted("remove", "user", user.target if isinstance(user, At) else user)


@matcher.assign("remove.group")
async def remove_group(group: str) -> None:
    set_trusted("remove", "group", group)


@matcher.assign("list.user")
async def list_user(bot: Bot) -> None:
    users = [
        user.partition(":")[2]
        for user in load_trust_data(use_cache=False).user
        if user.startswith(bot.type)
    ]
    await matcher.send(
        ("可信用户\n" + "\n".join(users)) if users else "没有可信用户",
        at_sender=True,
    )


@matcher.assign("list.group")
async def list_group(bot: Bot) -> None:
    groups = [
        group.partition(":")[2]
        for group in load_trust_data(use_cache=False).group
        if group.startswith(bot.type)
    ]
    await matcher.send(
        ("可信群组\n" + "\n".join(groups)) if groups else "没有可信群组",
        at_sender=True,
    )
