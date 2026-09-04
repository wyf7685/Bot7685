from collections.abc import Iterable

from apscheduler.triggers.cron import CronTrigger
from nonebot import get_driver, logger
from nonebot_plugin_apscheduler import scheduler

from src.service.uninfo_target import resolve_target

from .database import Read60sSchedule, get_schedule, list_schedules
from .service import get_read60s_msg


def _job_id(schedule_id: int) -> str:
    return f"read_60s_{schedule_id}"


async def _send_scheduled_read60s(schedule_id: int) -> None:
    schedule = await get_schedule(schedule_id)
    if schedule is None:
        return
    target = await resolve_target(schedule.session_persist_id)
    if target is None:
        logger.warning(
            f"Read60s schedule {schedule_id} references missing uninfo session "
            f"{schedule.session_persist_id}"
        )
        return
    await (await get_read60s_msg()).send(target)


def add_job(schedule: Read60sSchedule) -> None:
    scheduler.add_job(
        _send_scheduled_read60s,
        CronTrigger(hour=schedule.hour, minute=schedule.minute),
        args=(schedule.id,),
        id=_job_id(schedule.id),
        misfire_grace_time=60,
        replace_existing=True,
    )


def remove_jobs(schedule_ids: Iterable[int]) -> None:
    for schedule_id in schedule_ids:
        job_id = _job_id(schedule_id)
        if scheduler.get_job(job_id) is not None:
            scheduler.remove_job(job_id)


@get_driver().on_startup
async def setup_jobs() -> None:
    for schedule in await list_schedules():
        add_job(schedule)


__all__ = ["add_job", "remove_jobs"]
