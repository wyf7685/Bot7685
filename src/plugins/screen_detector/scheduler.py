import contextlib
from datetime import UTC, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_apscheduler import scheduler

from src.highlight import Highlight
from src.plugins.upload_cos import upload_cos

from .config import pkg_subs
from .detect import detector_client

DAILY_PACKAGE_TTL = 60 * 60 * 24 * 7  # 7 days


@scheduler.scheduled_job(CronTrigger(hour=23, minute=55), misfire_grace_time=60 * 4)
async def daily_package() -> None:
    subs = pkg_subs.load()
    if not subs:
        return

    dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    path = await detector_client.package(dt.astimezone(UTC))
    if path is None:
        logger.warning("打包检测结果失败")
        return

    try:
        url = await upload_cos(
            path, f"detector/daily-package-{dt:%Y-%m-%d}.zip", ttl=DAILY_PACKAGE_TTL
        )
        logger.opt(colors=True).info(f"每日打包完成: <c>{url}</>")
    except Exception:
        logger.exception("上传打包结果失败")
        return
    finally:
        with contextlib.suppress(Exception):
            path.unlink()

    url_exp = datetime.now() + timedelta(seconds=DAILY_PACKAGE_TTL)
    message = f"每日打包完成\n链接过期时间: {url_exp:%Y-%m-%d %H:%M:%S}\n\n{url}"
    for sub in subs:
        try:
            await UniMessage.text(message).send(Target.load(sub))
        except Exception:
            logger.opt(colors=True).exception(
                f"发送打包结果失败: {Highlight.apply(sub)}"
            )
