from typing import TYPE_CHECKING, Any

from nonebot import get_driver
from nonebot.plugin import get_plugin, get_plugin_by_module_name

from src.disposable import internal_dispose

if TYPE_CHECKING:
    from apscheduler.job import Job


def setup_job_disposer(job: "Job") -> None:
    if plugin := get_plugin_by_module_name(job.func.__module__):
        internal_dispose(plugin.id_, lambda: job.remove())


@get_driver().on_startup
async def _() -> None:
    if get_plugin("nonebot_plugin_apscheduler") is None:
        return

    from nonebot_plugin_apscheduler import scheduler

    for job in scheduler.get_jobs():
        setup_job_disposer(job)

    def patched_add_job(*args: Any, **kwargs: Any) -> "Job":  # pyright: ignore[reportExplicitAny]
        job = original(*args, **kwargs)
        setup_job_disposer(job)
        return job

    original = scheduler.add_job
    scheduler.add_job = patched_add_job
