from datetime import UTC, datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler

from src.service.s3 import get_s3_service
from src.service.uninfo_target import resolve_target

from .api import calc_stream_size, detector_client
from .database import list_subscriptions

DAILY_PACKAGE_TTL = 60 * 60 * 24 * 7  # 7 days


@scheduler.scheduled_job(CronTrigger(hour=23, minute=55), misfire_grace_time=60 * 4)
async def daily_package() -> None:
    subs = await list_subscriptions()
    if not subs:
        return

    dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    since = dt.astimezone(UTC)
    s3_key = f"detector/daily-package-{dt:%Y-%m-%d}.zip"
    async with calc_stream_size(detector_client.package(since)) as (stream, get_size):
        try:
            url = await get_s3_service().upload_temporary(
                stream,
                key=s3_key,
                expires_in=DAILY_PACKAGE_TTL,
            )
        except Exception:
            logger.exception("上传打包结果失败")
            return
        else:
            size = get_size() / 1024 / 1024
            logger.opt(colors=True).success(
                f"每日打包完成 "
                f"| 起始时间: <lg>{since.astimezone():%Y-%m-%d %H:%M:%S}</> "
                f"| 文件大小: <c>{size:.3f}</>MB "
                f"| Key: <y><i>{escape_tag(s3_key)}</></>"
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
            target = await resolve_target(sub.session_persist_id)
            if target is None:
                logger.warning(
                    f"截图订阅引用了不存在的 Session: {sub.session_persist_id}"
                )
                continue
            await UniMessage.text(message).send(target)
        except Exception:
            logger.opt(colors=True).exception(
                f"发送打包结果失败: subscription scene={sub.scene_persist_id}"
            )
