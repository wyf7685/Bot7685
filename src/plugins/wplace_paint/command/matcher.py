import hashlib
from typing import Annotated, Literal, NoReturn

from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    CommandMeta,
    Field,
    MsgTarget,
    MultiVar,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)

from ..scheduler import FETCH_INTERVAL_MINS

alc = Alconna(
    "wplace",
    Subcommand(
        "add",
        Args[
            "token",
            str,
            Field(completion=lambda: "wplace Cookies 中的 j (token)"),
        ][
            "cf_clearance",
            str,
            Field(completion=lambda: "wplace Cookies 中的 cf_clearance"),
        ],
        alias={"a"},
        help_text="添加一个 WPlace 账号",
    ),
    Subcommand(
        "query",
        Args["target?#查询目标", At | Literal["$group"]],
        alias={"q"},
        help_text="查询目标用户当前绑定的所有账号信息",
    ),
    Subcommand(
        "config",
        Args["identifier?#账号标识,ID或用户名", str],
        Option(
            "--notify-mins|-n",
            Args["notify_mins", int, Field(completion=lambda: "提前通知分钟数")],
            help_text=f"提前多少分钟通知 (默认10,最小{FETCH_INTERVAL_MINS})",
        ),
        Option(
            "--set-target",
            help_text="设置当前会话为推送目标",
        ),
        Option(
            "--max-overflow-notify|-m",
            Args[
                "max_overflow_notify",
                int,
                Field(completion=lambda: "最大溢出通知次数 (默认3次, 0为禁用)"),
            ],
            help_text="设置最大溢出通知次数 (默认3次, 0为禁用)",
        ),
        Option(
            "--target-droplets|-t",
            Args["target_droplets?#目标droplets值", int],
            help_text="设置目标droplets值,查询时显示达成时间(不附带参数则取消设置)",
        ),
        alias={"c"},
        help_text="修改已绑定账号的配置",
    ),
    Subcommand(
        "remove",
        Args["identifier?#账号标识,ID或用户名", str],
        alias={"rm"},
        help_text="移除已绑定的账号",
    ),
    Subcommand(
        "bind",
        Args["identifier?#账号标识,ID或用户名", str],
        help_text="将账号绑定到当前群组(使其对$group可见)",
    ),
    Subcommand(
        "preview",
        Args[
            "coord1#对角坐标1",
            str,
            Field(completion=lambda: "第一个坐标(选点并复制BlueMarble的坐标)"),
        ][
            "coord2#对角坐标2",
            str,
            Field(completion=lambda: "第二个坐标(选点并复制BlueMarble的坐标)"),
        ],
        Option("--background|-b", Args["background#背景色RGB", str]),
        help_text="获取指定区域的预览图",
    ),
    Subcommand(
        "rank",
        Subcommand(
            "bind",
            Option("--revoke|-r", help_text="取消当前会话的区域 ID 绑定"),
            Args[
                "coord1#对角坐标1",
                str,
                Field(completion=lambda: "第一个坐标(选点并复制BlueMarble的坐标)"),
            ][
                "coord2#对角坐标2",
                str,
                Field(completion=lambda: "第二个坐标(选点并复制BlueMarble的坐标)"),
            ],
        ),
        Subcommand(
            "query",
            Args[
                "rank_type",
                Literal["today", "week", "month", "all"],
                Field(completion=lambda: "排行榜类型(today/week/month/all)"),
            ],
            Option("--all-users|-a"),
            help_text="查询指定区域的排行榜",
        ),
        help_text="排行榜功能",
    ),
    Subcommand(
        "template",
        Subcommand(
            "bind",
            Option("--revoke|-r", help_text="取消当前会话的模板绑定"),
        ),
        Subcommand(
            "preview",
            Option("--background|-b", Args["background#背景色RGB", str]),
            help_text="预览当前会话绑定的模板",
        ),
        Subcommand("progress", help_text="查询模板的绘制进度"),
        Subcommand(
            "color",
            Args["color_name", MultiVar(str), Field(completion=lambda: "颜色名称")],
            Option("--background|-b", Args["background#背景色RGB", str]),
            help_text="选择模板中指定的颜色并渲染",
        ),
        Subcommand(
            "locate",
            Args["color_name", str, Field(completion=lambda: "颜色名称")],
            Option("-n", Args["max_count?#最大数量", int]),
            help_text="查询模板中指定颜色的像素位置",
        ),
        alias={"tp"},
        help_text="模板相关功能",
    ),
    Subcommand(
        "find-color",
        Args["color_name", str, Field(completion=lambda: "颜色名称")],
        help_text="查询当前群组中拥有指定颜色的用户",
    ),
    meta=CommandMeta(
        description="WPlace 查询",
        usage="wplace <add|query|config|remove> [参数...]",
        author="wyf7685",
    ),
)
matcher = on_alconna(
    alc,
    aliases={"wp"},
    comp_config={"lite": True},
    skip_for_unmatch=False,
    use_cmd_start=True,
)
matcher.shortcut("wpq", {"command": "wplace query {*}"})
matcher.shortcut("wpg", {"command": "wplace query $group"})
matcher.shortcut("wpr", {"command": "wplace rank query {*}"})
matcher.shortcut("wpt", {"command": "wplace template progress"})


async def finish(msg: str | UniMessage) -> NoReturn:
    await (UniMessage.text(msg) if isinstance(msg, str) else msg).finish(reply_to=True)


async def prompt(msg: str) -> str:
    resp = await matcher.prompt(msg + "\n(回复 “取消” 以取消操作)")
    if resp is None:
        await finish("操作已取消")
    text = resp.extract_plain_text().strip()
    if text == "取消":
        await finish("操作已取消")
    return text


def target_hash(target: MsgTarget) -> str:
    args = (target.id, target.channel, target.private, target.self_id)
    for k, v in target.extra.items():
        args += (k, v)
    key = "".join(map(str, args)).encode("utf-8")
    return hashlib.sha256(key).hexdigest()


TargetHash = Annotated[str, Depends(target_hash)]
