from nonebot import require

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_chatrecorder")
require("nonebot_plugin_htmlrender")
require("nonebot_plugin_orm")
require("nonebot_plugin_uninfo")
from nonebot.params import Depends
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    MsgTarget,
    Option,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

require("src.plugins.trusted")
from src.plugins.trusted import TrustedUser

from .query import query_scene, query_session
from .render import render_my, render_scene
from .scheduler import add_job, clear_job

alc = Alconna(
    "talk_stats",
    Subcommand(
        "my",
        Option("--days|-d", Args["days?#天数", int]),
        help_text="查询我的水群瓷砖",
    ),
    Subcommand(
        "scene",
        Option("days|--days|-d", Args["days#天数", int]),
        Option("--num|-n", Args["num#人数", int]),
        help_text="查询群聊活跃度排行",
    ),
    Subcommand(
        "schedule",
        Subcommand(
            "add",
            Args["hour?#小时", int]["minute?#分钟", int],
            Option("--num|-n", Args["num#人数", int]),
            help_text="添加定时任务",
        ),
        Subcommand("clear", help_text="清空定时任务"),
        help_text="设置群聊活跃度排行定时任务",
    ),
    meta=CommandMeta(
        description="群聊活跃度统计",
        usage="talk_stats -h",
        example="talk_stats my -d 30\n"
        "talk_stats scene -d 7 -n 5\n"
        "talk_stats schedule add 23 59 -n 5",
        author="wyf7685",
    ),
)


@Depends
async def _check_group(target: MsgTarget) -> None:
    if target.private:
        await UniMessage.text("该命令只能在群聊中使用").send()
        matcher.skip()


matcher = on_alconna(alc, permission=TrustedUser())
matcher.shortcut(
    r"我的水群瓷砖",
    {"command": "talk_stats my {*}"},
)


@matcher.assign("my", parameterless=[_check_group])
async def assign_my(session: Uninfo, days: int = 90) -> None:
    days = max(90, days)
    data = await query_session(session, days)
    raw = await render_my(data, days, session.user)
    await UniMessage.image(raw=raw).finish(reply_to=True)


@matcher.assign("scene", parameterless=[_check_group])
async def assign_scene(session: Uninfo, days: int = 7, num: int = 5) -> None:
    data = await query_scene(session, days, max(3, num))
    raw = await render_scene(data, days)
    await UniMessage.image(raw=raw).finish(reply_to=True)


@matcher.assign("schedule.add", parameterless=[_check_group])
async def assign_schedule_add(
    session: Uninfo,
    target: MsgTarget,
    num: int = 5,
    hour: int = 23,
    minute: int = 59,
) -> None:
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await UniMessage.text("时间错误，请输入正确的时间").finish()

    add_job(session, target, num, hour, minute)
    await UniMessage.text(
        f"已添加定时任务，每日{hour}点{minute}分发送群聊活跃度排行前{num}名"
    ).finish()


@matcher.assign("schedule.clear", parameterless=[_check_group])
async def assign_schedule_clear(target: MsgTarget) -> None:
    clear_job(target)
    await UniMessage.text("已清空定时任务").finish()
