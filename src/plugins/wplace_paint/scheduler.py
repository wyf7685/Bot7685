# ruff: noqa: FBT003
import hashlib

import anyio
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler

from src.plugins.cache import get_cache

from .config import ConfigModel, config
from .fetch import FetchFailed, fetch_me

push_cache = get_cache[str, bool]("wplace_paint:push")


async def fetch_for_user(config: ConfigModel) -> None:
    # fetch user info
    logger.info(f"正在获取用户 {config.user_id} 的信息")
    try:
        resp = await fetch_me(
            config.token,
            config.cf_clearance,
        )
    except FetchFailed as e:
        logger.warning(f"获取用户 {config.user_id} 的信息失败: {e.msg}")
        return
    except Exception:
        logger.opt(exception=True).warning(
            f"获取用户 {config.user_id} 的信息时发生意外错误"
        )
        return

    # calc remaining
    remaining = resp.charges.remaining_secs()
    if remaining > config.notify_mins:
        logger.info(f"用户 {config.user_id} 还剩 {remaining:.0f} 秒，跳过通知")
        return

    # check whether should push
    cache_key = hashlib.sha256(f"{config.user_id}${resp.id}".encode()).hexdigest()
    if not await push_cache.get(cache_key, True):
        logger.info(f"用户 {config.user_id} 跳过通知")
        return

    # format message
    msg = UniMessage.text(resp.format_notification())
    if not config.target.private:
        msg = UniMessage.at(config.user_id) + msg

    # send notification
    try:
        await msg.send(target=config.target)
    except Exception:
        logger.opt(exception=True).warning(f"向用户 {config.user_id} 发送通知失败")

    await push_cache.set(cache_key, False)


async def _job() -> None:
    async with anyio.create_task_group() as tg:
        for cfg in config.load():
            tg.start_soon(fetch_for_user, cfg)


scheduler.add_job(
    _job,
    CronTrigger(minute="*/10"),
    misfire_grace_time=300,
    max_instances=1,
    id="wplace_paint_fetcher",
)
