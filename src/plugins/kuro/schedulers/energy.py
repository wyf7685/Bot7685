import datetime
import random

import anyio
import nonebot
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

from ..database.kuro_token import KuroToken, get_target, list_all_token
from ..handler import KuroHandler

logger = nonebot.logger.opt(colors=True)
last_push: dict[int, float] = {}


async def push_msg(handler: KuroHandler, kuro_token: KuroToken) -> None:
    user_id = kuro_token.user_id
    now = datetime.datetime.now().timestamp()

    if user_id not in last_push or now - last_push[user_id] > 60 * 10:
        try:
            await handler.push_msg(await get_target(kuro_token))
        except Exception as err:
            logger.warning(f"库洛体力推送出错: {err}")

        last_push[user_id] = now


@scheduler.scheduled_job(CronTrigger(minute="*/30"), misfire_grace_time=60)
async def auto_energy() -> None:
    for kuro_token in await list_all_token():
        handler = KuroHandler(kuro_token.token)
        should_push = False
        try:
            should_push = await handler.check_energy()
        except Exception as err:
            logger.warning(f"鸣潮结波晶片推送出错: {err}")

        if should_push:
            await push_msg(handler, kuro_token)

        await anyio.sleep(random.randint(2, 5))
