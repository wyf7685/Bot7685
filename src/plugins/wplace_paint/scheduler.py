# ruff: noqa: FBT003
import hashlib

import anyio
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler

from src.plugins.cache import get_cache

from .config import ConfigModel, config
from .fetch import FetchFailed, fetch_me

push_cache = get_cache[str, bool]("wplace_paint:push")
logger = logger.opt(colors=True)


async def fetch_for_user(config: ConfigModel) -> None:
    colored_user = (
        f"用户 <c>{config.user_id}</> "
        f"[<y>{config.wp_user_name}</>(<c>{config.wp_user_id}</>)]"
    )

    # fetch user info
    logger.info(f"正在获取 {colored_user} 的信息")
    try:
        resp = await fetch_me(config)
    except FetchFailed as e:
        logger.warning(f"获取 {colored_user} 的信息失败: {escape_tag(e.msg)}")
        return
    except Exception:
        logger.opt(exception=True).warning(f"获取 {colored_user} 的信息时发生意外错误")
        return

    cache_key = hashlib.sha256(f"{config.user_id}${resp.id}".encode()).hexdigest()

    # calc remaining
    remaining = resp.charges.remaining_secs()
    if remaining > config.notify_mins * 60:
        logger.info(f"{colored_user} 还剩 {remaining:.0f} 秒，跳过通知")
        await push_cache.set(cache_key, True)
        return

    # check whether should push
    if not await push_cache.get(cache_key, True):
        logger.info(f"{colored_user} 跳过通知")
        return

    # format message
    msg = UniMessage.text(resp.format_notification())
    if not config.target.private:
        msg = UniMessage.at(config.user_id) + msg

    # send notification
    max_attempt = 3
    for attempt in range(max_attempt):
        try:
            await msg.send(target=config.target)
        except Exception:
            log_msg = f"向 {colored_user} 推送通知失败 ({attempt + 1}/{max_attempt})"
            if attempt == max_attempt - 1:
                logger.opt(exception=True).warning(log_msg)
                return
            logger.warning(log_msg)
            await anyio.sleep(5)
        else:
            await push_cache.set(cache_key, False)
            break


async def _job() -> None:
    async with anyio.create_task_group() as tg:
        for cfg in config.load():
            tg.start_soon(fetch_for_user, cfg)


scheduler.add_job(
    _job,
    CronTrigger(minute="*/5"),
    misfire_grace_time=60,
    max_instances=1,
    id="wplace_paint_fetcher",
)
