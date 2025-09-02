import hashlib
from datetime import datetime, timedelta
from typing import NoReturn

import anyio
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_apscheduler import scheduler
from pydantic import BaseModel

from src.plugins.cache import get_cache

from .config import ConfigModel, config
from .fetch import RequestFailed, fetch_me

FETCH_INTERVAL_MINS = 5
MAX_PUSH_ATTEMPT = 3
push_cache = get_cache[str, str]("wplace_paint:push_state")
logger = logger.opt(colors=True)


class PushState(BaseModel):
    last_notification: datetime | None = None
    overflow: datetime | None = None
    overflow_notify_count: int = 0

    @classmethod
    async def load(cls, key: str) -> "PushState":
        return cls.model_validate_json(await push_cache.get(key, "{}"))

    async def save(self, key: str) -> None:
        await push_cache.set(key, self.model_dump_json())


class FetchDone(Exception): ...


async def fetch_for_user(config: ConfigModel) -> None:
    colored_user = (
        f"用户 <c>{config.user_id}</> "
        f"[<y>{config.wp_user_name}</>(<c>{config.wp_user_id}</>)]"
    )

    # 获取用户信息
    logger.debug(f"正在获取 {colored_user} 的信息")
    try:
        resp = await fetch_me(config)
    except RequestFailed as e:
        logger.warning(f"获取 {colored_user} 的信息失败: {escape_tag(e.msg)}")
        return
    except Exception:
        logger.opt(exception=True).warning(f"获取 {colored_user} 的信息时发生意外错误")
        return

    # 读取缓存
    cache_key = hashlib.sha256(f"{config.user_id}${resp.id}".encode()).hexdigest()
    cache = await PushState.load(cache_key)

    async def push() -> NoReturn:
        msg = (
            UniMessage
            if config.target.private
            else UniMessage.at(config.user_id).text("\n")
        ).text(resp.format_notification(config.target_droplets))

        for attempt in range(MAX_PUSH_ATTEMPT):
            try:
                await msg.send(target=config.target)
            except Exception:
                attempts = f"(<y>{attempt + 1}</>/<y>{MAX_PUSH_ATTEMPT}</>)"
                log_msg = f"向 {colored_user} 推送通知失败 {attempts}"
                if attempt == MAX_PUSH_ATTEMPT - 1:
                    logger.opt(exception=True).warning(log_msg)
                    raise FetchDone from None
                logger.warning(log_msg)
                await anyio.sleep(5)
            else:
                logger.info(f"已向 {colored_user} 推送通知")
                break

        cache.last_notification = datetime.now()
        await cache.save(cache_key)
        raise FetchDone

    # 计算剩余时间
    remaining = resp.charges.remaining_secs()

    # 正常状态
    if remaining > 0:
        # 重置溢出状态
        if cache.overflow is not None:
            cache.overflow = None
            cache.overflow_notify_count = 0
            await cache.save(cache_key)

        # 无需推送
        if remaining > config.notify_mins * 60:
            cache.last_notification = None
            await cache.save(cache_key)
            logger.debug(f"{colored_user} 还剩 {remaining:.0f} 秒，跳过通知")
            return

        # 近期已通知
        if cache.last_notification is not None:
            logger.debug(f"{colored_user} 近期已通知，跳过通知")
            return

        # 执行推送
        logger.info(f"{colored_user} 剩余时间 {remaining:.0f} 秒，准备推送")
        await push()

    # 如果用户禁用了溢出通知，则直接返回
    if not config.max_overflow_notify:
        logger.debug(f"{colored_user} 已禁用溢出通知，跳过")
        return

    # 记录溢出开始时间
    cache.overflow = cache.overflow or datetime.now()

    # 首次溢出通知
    if cache.last_notification is None:
        cache.overflow_notify_count = 1
        logger.info(f"{colored_user} 首次溢出，准备推送")
        await push()

    # 已达到最大通知次数
    if cache.overflow_notify_count >= config.max_overflow_notify:
        logger.info(
            f"{colored_user} 溢出通知已达最大次数"
            f"({config.max_overflow_notify})，跳过通知"
        )
        return

    # 溢出通知逻辑
    last_notif_delta = datetime.now() - cache.last_notification
    hours_since_overflow = (datetime.now() - cache.overflow).total_seconds() / 3600

    # 根据溢出时长确定通知频率
    if hours_since_overflow <= 1:
        # 溢出1小时内，无需额外通知
        logger.info(f"{colored_user} 溢出未满1小时，跳过通知")
        return
    if (
        # 溢出1-4小时，每小时通知一次
        (hours_since_overflow <= 4 and last_notif_delta >= timedelta(hours=1))
        # 溢出4-12小时，每2小时通知一次
        or (hours_since_overflow <= 12 and last_notif_delta >= timedelta(hours=2))
        # 溢出12小时以上，每4小时通知一次
        or (hours_since_overflow > 12 and last_notif_delta >= timedelta(hours=4))
    ):
        cache.overflow_notify_count += 1
        logger.info(f"{colored_user} 已溢出 {hours_since_overflow:.1f} 小时，准备推送")
        await push()


@scheduler.scheduled_job(
    CronTrigger(minute=f"*/{FETCH_INTERVAL_MINS}"),
    misfire_grace_time=60,
    max_instances=1,
    id="wplace_paint_fetcher",
)
async def job() -> None:
    async def wrapper(cfg: ConfigModel) -> None:
        try:
            await fetch_for_user(cfg)
        except FetchDone:
            pass
        except Exception:
            logger.exception(f"处理用户 {cfg.user_id} 时发生错误")

    async with anyio.create_task_group() as tg:
        for cfg in config.load():
            tg.start_soon(wrapper, cfg)
