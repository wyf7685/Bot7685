from nonebot import logger
from nonebot_plugin_apscheduler import scheduler

from .exceptions import S3ConfigurationError
from .service import get_s3_service


@scheduler.scheduled_job(
    "interval",
    minutes=10,
    id="s3_temporary_object_cleanup",
    max_instances=1,
    coalesce=True,
)
async def cleanup_temporary_objects() -> None:
    try:
        await get_s3_service().cleanup_expired()
    except S3ConfigurationError:
        return
    except Exception:
        logger.exception("S3 temporary-object cleanup failed")


__all__ = []
