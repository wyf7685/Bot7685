import hashlib
import random
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

from .config import UserConfig, users
from .fetch import RequestFailed, fetch_me

FETCH_INTERVAL_MINS = 5
LAZY_FETCH_INTERVAL = timedelta(minutes=29)
MAX_PUSH_ATTEMPT = 3
push_cache = get_cache[str, str]("wplace_paint:push_state")
logger = logger.opt(colors=True)


def calc_cache_key(cfg: UserConfig) -> str:
    return hashlib.sha256(f"{cfg.user_id}${cfg.wp_user_id}".encode()).hexdigest()


class PushState(BaseModel):
    last_notification: datetime | None = None
    overflow: datetime | None = None
    overflow_notify_count: int = 0
    credential_invalid: bool = False

    @classmethod
    async def load(cls, key: str) -> "PushState":
        return cls.model_validate_json(await push_cache.get(key, "{}"))

    async def save(self, key: str) -> None:
        await push_cache.set(key, self.model_dump_json(), ttl=timedelta(hours=1))


async def expire_push_cache(cfg: UserConfig) -> None:
    key = calc_cache_key(cfg)
    if await push_cache.exists(key):
        await push_cache.delete(key)


class FetchDone(Exception): ...


async def fetch_for_user(cfg: UserConfig) -> None:
    if not cfg.wp_user_id:
        return

    cache_key = calc_cache_key(cfg)
    cache = await PushState.load(cache_key)

    colored = (
        f"用户 <c>{cfg.user_id}</> [<y>{cfg.wp_user_name}</> #<c>{cfg.wp_user_id}</>]"
    )

    if cache.credential_invalid:
        logger.debug(f"用户 {colored} 凭据已失效，跳过获取")
        return

    if (
        cache.overflow is not None
        and cache.last_notification is not None
        and datetime.now() - cache.last_notification < LAZY_FETCH_INTERVAL
    ):
        logger.debug(f"用户 {colored} 已溢出且近期已通知，跳过获取")
        return

    def finish() -> NoReturn:
        raise FetchDone from None

    async def save_cache() -> None:
        await cache.save(cache_key)

    async def _push_msg(text: str) -> NoReturn:
        target = cfg.target
        try:
            bot = await target.select()
        except Exception:
            logger.warning(f"获取 {colored} 的发送目标失败，跳过通知")
            finish()

        if cfg.adapter is not None and bot.type != cfg.adapter:
            logger.warning(f"{colored} 绑定的适配器不匹配，跳过通知")
            finish()

        msg = (
            UniMessage()
            if cfg.target.private
            else UniMessage.at(cfg.user_id).text("\n")
        ).text(text)
        for attempt in range(MAX_PUSH_ATTEMPT):
            try:
                await msg.send(target=target, bot=bot)
            except Exception:
                log_msg = (
                    f"向 {colored} 推送通知失败 "
                    f"(<y>{attempt + 1}</>/<y>{MAX_PUSH_ATTEMPT}</>)"
                )
                if attempt == MAX_PUSH_ATTEMPT - 1:
                    logger.opt(colors=True, exception=True).warning(log_msg)
                    finish()
                logger.warning(log_msg)
                await anyio.sleep(5)
            else:
                logger.info(f"已向 {colored} 推送通知")
                break

        cache.last_notification = datetime.now()
        await save_cache()
        finish()

    async def push_notification() -> NoReturn:
        await _push_msg(resp.format_notification(cfg.target_droplets))

    async def push_credential_expired() -> NoReturn:
        logger.info(f"{colored} 凭据无效，准备推送")
        cache.credential_invalid = True
        await _push_msg(
            f"用户 <c>{cfg.user_id}</> "
            f"[<y>{cfg.wp_user_name}</> #<c>{cfg.wp_user_id}</>] "
            "的 wplace 凭据已失效，请重新绑定"
        )

    async def check_overflow() -> NoReturn:
        # 记录溢出开始时间
        if cache.overflow is None:
            cache.overflow = datetime.now()
            cache.last_notification = None
            await save_cache()

        # 首次溢出通知
        if cache.last_notification is None:
            cache.overflow_notify_count = 1
            logger.info(f"{colored} 首次溢出，准备推送")
            await push_notification()

        # 已达到最大通知次数
        if cache.overflow_notify_count >= cfg.max_overflow_notify:
            logger.info(
                f"{colored} 溢出通知已达最大次数({cfg.max_overflow_notify})，跳过通知"
            )
            finish()

        # 溢出通知逻辑
        last_notif_delta = datetime.now() - cache.last_notification
        hours_since_overflow = (datetime.now() - cache.overflow).total_seconds() / 3600

        # 根据溢出时长确定通知频率
        if hours_since_overflow < 0.5:
            # 溢出半小时内，无需额外通知
            logger.info(f"{colored} 溢出未满半小时，跳过通知")
            finish()

        if (
            # 溢出1小时内，每30分钟通知一次
            (hours_since_overflow <= 1 and last_notif_delta >= timedelta(minutes=30))
            # 溢出1-4小时，每小时通知一次
            or (hours_since_overflow <= 4 and last_notif_delta >= timedelta(hours=1))
            # 溢出4-12小时，每2小时通知一次
            or (hours_since_overflow <= 12 and last_notif_delta >= timedelta(hours=2))
            # 溢出12小时以上，每4小时通知一次
            or (hours_since_overflow > 12 and last_notif_delta >= timedelta(hours=4))
        ):
            cache.overflow_notify_count += 1
            logger.info(f"{colored} 已溢出 {hours_since_overflow:.1f} 小时，准备推送")
            await push_notification()

        finish()

    # 获取用户信息
    logger.debug(f"正在获取 {colored} 的信息")
    try:
        resp = await fetch_me(cfg)
    except RequestFailed as e:
        logger.warning(f"获取 {colored} 的信息失败: {escape_tag(e.msg)}")
        if e.status_code == 500:
            await push_credential_expired()
        finish()
    except Exception:
        logger.opt(exception=True).warning(f"获取 {colored} 的信息时发生意外错误")
        finish()

    # 计算剩余时间
    remaining = resp.charges.remaining_secs()

    # 溢出状态
    if remaining <= 0:
        if cfg.max_overflow_notify:
            # 执行溢出通知逻辑
            await check_overflow()
        else:
            # 如果用户禁用了溢出通知，则直接结束
            logger.debug(f"{colored} 已禁用溢出通知，跳过")
            finish()

    # 正常状态
    if cache.overflow is not None:
        # 重置溢出状态
        cache.overflow = None
        cache.overflow_notify_count = 0
        await save_cache()

    # 无需推送
    if remaining > cfg.notify_mins * 60:
        cache.last_notification = None
        logger.debug(f"{colored} 还剩 {remaining:.0f} 秒，跳过通知")
        finish()

    # 近期已通知
    if cache.last_notification is not None:
        logger.debug(f"{colored} 近期已通知，跳过通知")
        finish()

    # 执行推送
    logger.info(f"{colored} 剩余时间 {remaining:.0f} 秒，准备推送")
    await push_notification()


@scheduler.scheduled_job(
    CronTrigger(minute=f"*/{FETCH_INTERVAL_MINS}"),
    misfire_grace_time=60,
    max_instances=1,
    id="wplace_paint_fetcher",
)
async def job() -> None:
    async def wrapper(cfg: UserConfig, delay: float) -> None:
        await anyio.sleep(delay)

        try:
            await fetch_for_user(cfg)
        except FetchDone:
            pass
        except Exception:
            logger.exception(f"处理用户 {cfg.user_id} 时发生错误")

    async with anyio.create_task_group() as tg:
        for cfg in users.load():
            tg.start_soon(wrapper, cfg, random.uniform(0, 3 * 60))
