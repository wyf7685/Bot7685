import random

import anyio
import nonebot
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

from ..config import config
from ..database.kuro_token import get_target, list_all_token
from ..handler import KuroHandler

logger = nonebot.logger.opt(colors=True)


@scheduler.scheduled_job(
    trigger=CronTrigger(
        hour=config.auto_signin.hour,
        minute=config.auto_signin.minute,
    ),
    misfire_grace_time=60,
)
async def auto_signin() -> None:
    for kuro_token in await list_all_token():
        handler = KuroHandler(kuro_token.token)
        try:
            await handler.do_signin()
        except Exception as err:
            logger.opt(exception=err).warning(f"{kuro_token.kuro_id} 签到失败: {err}")
        else:
            try:
                await handler.push_msg(await get_target(kuro_token))
            except Exception as err:
                logger.opt(exception=err).warning(
                    f"{kuro_token.kuro_id} 发送通知失败: {err}"
                )
        finally:
            await anyio.sleep(random.randint(2, 5))
