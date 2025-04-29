# ruff: noqa: FBT003
import random

import anyio
import nonebot
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

from src.plugins.cache import get_cache

from ..database.kuro_token import get_target, list_all_token
from ..handler import KuroHandler

logger = nonebot.logger.opt(colors=True)
push_cache = get_cache("kuro:energy")


@scheduler.scheduled_job(CronTrigger(minute="*/30"), misfire_grace_time=60)
async def auto_energy() -> None:
    for kuro_token in await list_all_token():
        handler = KuroHandler(kuro_token.token)
        try:
            need_push = await handler.check_energy()
        except Exception as err:
            need_push = False
            logger.warning(f"鸣潮结波晶片获取出错: {err}")

        if need_push and await push_cache.get(kuro_token.user_id, True):
            try:
                await handler.push_msg(await get_target(kuro_token))
                await push_cache.set(kuro_token.user_id, False)
            except Exception as err:
                logger.warning(f"鸣潮结波晶片推送出错: {err}")
        elif not need_push:
            await push_cache.set(kuro_token.user_id, True)

        await anyio.sleep(random.randint(2, 5))
