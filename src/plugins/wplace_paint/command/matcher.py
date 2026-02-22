from typing import Literal, NoReturn

from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Field,
    MultiVar,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)

alc = Alconna(
    "wplace",
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
            Option("--template|-t", help_text="根据当前会话的模板绑定区域 ID"),
        ),
        Subcommand(
            "query",
            Args[
                "rank_type",
                Literal["today", "week", "month", "all"],
                Field(completion=lambda: "排行榜类型(today/week/month/all)"),
            ],
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
            Option("--border-pixels|-p", Args["pixels#边框像素", int]),
            Option("--overlay", Args["overlay_alpha?#覆盖层透明度", int]),
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
            Option("-n", Args["max_count#最大数量", int, Field(default=5)]),
            help_text="查询模板中指定颜色的像素位置",
        ),
        alias={"tp"},
        help_text="模板相关功能",
    ),
    meta=CommandMeta(
        description="WPlace 辅助",
        usage="wplace <template|rank|preview> [params...]",
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
