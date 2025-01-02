from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    CommandMeta,
    Subcommand,
    on_alconna,
)

from .trust_data import set_trusted

matcher = on_alconna(
    Alconna(
        "trust",
        Subcommand(
            "add",
            Subcommand("user", Args["user", At | str]),
            Subcommand("group", Args["group", str]),
        ),
        Subcommand(
            "remove",
            Subcommand("user", Args["user", At | str]),
            Subcommand("group", Args["group", str]),
            alias={"rm"},
        ),
        meta=CommandMeta(
            description="Manage trusted user or group",
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
