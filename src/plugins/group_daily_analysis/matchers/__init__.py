"""命令注册和生命周期钩子。"""

from nonebot import get_driver

from .analysis import matcher as analysis  # noqa: F401
from .scheduler_hook import setup_scheduled_jobs

driver = get_driver()


@driver.on_startup
async def _on_startup() -> None:
    """启动时注册定时任务。"""
    setup_scheduled_jobs()
