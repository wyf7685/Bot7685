from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Option,
    Subcommand,
    on_alconna,
    store_true,
)

alc = Alconna(
    "kuro",
    Subcommand(
        "token",
        Subcommand(
            "add",
            Args["token?#库街区token", str],
            Option("-n|--note", Args["note#备注", str]),
            help_text="添加账号",
        ),
        Subcommand(
            "remove",
            Args["key#库洛ID或备注", str],
            alias={"rm", "del"},
            help_text="移除账号",
        ),
        Subcommand(
            "list",
            Option(
                "-a|--all",
                action=store_true,
                default=False,
                help_text="[superuser] 列出所有 token",
            ),
            alias={"ls"},
            help_text="列出已绑定的账号",
        ),
        Subcommand(
            "update",
            Args["key#库洛ID或备注", str],
            Option(
                "--token|-t",
                Args["token#库街区token", str],
                help_text="指定更新 token",
            ),
            Option(
                "--note|-n",
                Args["note#备注", str],
                help_text="指定更新备注",
            ),
            help_text="更新账号信息",
        ),
        help_text="管理库街区账号",
    ),
    Subcommand(
        "signin",
        Args["key#库洛ID或备注", str],
        Option("--kuro|-k", help_text="库街区社区签到"),
        Option("--pns|-p", help_text="战双游戏签到"),
        Option("--wuwa|-w|--mc|-m", help_text="鸣潮游戏签到"),
    ),
    meta=CommandMeta(
        description="库洛插件",
        usage="kuro -h",
        author="wyf7685",
    ),
)

root_matcher = on_alconna(alc)