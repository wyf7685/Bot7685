from datetime import UTC, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_apscheduler import scheduler

from src.highlight import Highlight
from src.plugins.upload_cos import upload_cos

from .api import calc_stream_size, detector_client
from .config import pkg_subs

DAILY_PACKAGE_TTL = 60 * 60 * 24 * 7  # 7 days


@scheduler.scheduled_job(CronTrigger(hour=23, minute=55), misfire_grace_time=60 * 4)
async def daily_package() -> None:
    subs = pkg_subs.load()
    if not subs:
        return

    dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = dt.astimezone(UTC)
    cos_key = f"detector/daily-package-{dt:%Y-%m-%d}.zip"
    async with calc_stream_size(detector_client.package(since)) as (stream, get_size):
        try:
            url = await upload_cos(stream, cos_key, ttl=DAILY_PACKAGE_TTL)
        except Exception:
            logger.exception("上传打包结果失败")
            return
        else:
            size = get_size() / 1024 / 1024
            logger.opt(colors=True).success(
                f"每日打包完成 "
                f"| 起始时间: <lg>{since.astimezone():%Y-%m-%d %H:%M:%S}</> "
                f"| 文件大小: <c>{size:.3f}</>MB "
                f"| URL: <y><i>{escape_tag(url)}</></>"
            )

    url_exp = datetime.now() + timedelta(seconds=DAILY_PACKAGE_TTL)
    message = (
        f"每日打包完成\n"
        f"链接过期时间: {url_exp:%Y-%m-%d %H:%M:%S}\n"
        f"文件大小: {size:.3f} MB\n"
        f"\n{url}"
    )

    for sub in subs:
        try:
            await UniMessage.text(message).send(Target.load(sub))
        except Exception:
            logger.opt(colors=True).exception(
                f"发送打包结果失败: {Highlight.apply(sub)}"
            )
