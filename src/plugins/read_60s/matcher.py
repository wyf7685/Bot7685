from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Subcommand,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from src.plugins.trusted import TrustedUser
from src.service.uninfo_target import persist_session_reference

from .database import (
    Read60sSchedule,
    add_schedule,
    find_schedule,
    list_schedules,
    remove_schedules,
)
from .scheduler import add_job, remove_jobs
from .service import get_read60s_msg

matcher = on_alconna(
    Alconna(
        "read60s",
        Subcommand(
            "add",
            Args["hour", int]["minute", int],
            help_text="在当前会话添加定时任务",
        ),
        Subcommand("clear", help_text="清空当前会话的定时任务"),
        Subcommand("list", help_text="查看定时任务"),
        Subcommand("get", help_text="获取今日60S读世界"),
        meta=CommandMeta(
            description="每日60S读世界",
            usage="read60s add [hour] [minute]\nread60s <clear|list|get>",
            example="read60s add 8 0\nread60s clear\nread60s list\nread60s get",
            author="wyf7685",
        ),
    ),
    permission=TrustedUser(),
)


@matcher.assign("~add")
async def assign_add(session: Uninfo, hour: int, minute: int) -> None:
    if not (0 <= hour < 24 and 0 <= minute < 60):
        await UniMessage.text("时间格式错误，请输入正确的时间").finish()

    reference = await persist_session_reference(session)
    if await find_schedule(reference.scene_persist_id, hour, minute) is not None:
        await UniMessage.text("当前会话已存在相同时间的定时任务").finish()

    schedule = Read60sSchedule(
        session_persist_id=reference.session_persist_id,
        scene_persist_id=reference.scene_persist_id,
        hour=hour,
        minute=minute,
    )
    await add_schedule(schedule)
    add_job(schedule)
    await UniMessage.text(
        f"已添加定时任务，每日{hour}点{minute}分发送60S读世界"
    ).finish()


@matcher.assign("~clear")
async def assign_clear(session: Uninfo) -> None:
    reference = await persist_session_reference(session)
    remove_jobs(await remove_schedules(reference.scene_persist_id))
    await UniMessage.text("已清空当前会话的定时任务").finish()


@matcher.assign("~list")
async def assign_list(session: Uninfo) -> None:
    reference = await persist_session_reference(session)
    schedules = await list_schedules(scene_persist_id=reference.scene_persist_id)
    if not schedules:
        await UniMessage.text("当前会话没有定时任务").finish()

    lines = ["当前会话的定时任务:", ""]
    lines.extend(
        f"{index}. {schedule.hour:02}:{schedule.minute:02}"
        for index, schedule in enumerate(schedules, 1)
    )
    await UniMessage.text("\n".join(lines)).finish()


@matcher.assign("~get")
async def assign_get() -> None:
    await (await get_read60s_msg()).finish()


__all__ = ["matcher"]
