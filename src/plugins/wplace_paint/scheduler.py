import contextlib
import hashlib
import random
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import NoReturn

import anyio
from apscheduler.triggers.cron import CronTrigger
from nonebot import logger
from nonebot.adapters import Bot
from nonebot.utils import escape_tag
from nonebot_plugin_alconna import Target, UniMessage
from nonebot_plugin_apscheduler import scheduler
from pydantic import BaseModel

from src.plugins.cache import get_cache

from .config import UserConfig, users
from .fetch import FetchMeResponse, RequestFailed, fetch_me

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


class Fetcher:
    def __init__(self, cfg: UserConfig) -> None:
        self.cfg = cfg
        self._cache_key = self._cache = None

    @property
    def colored(self) -> str:
        return (
            f"用户 <c>{self.cfg.user_id}</> "
            f"[<y>{self.cfg.wp_user_name}</> #<c>{self.cfg.wp_user_id}</>]"
        )

    def finish(self) -> NoReturn:
        raise FetchDone from None

    async def _save_cache(self) -> None:
        assert self._cache_key is not None, "Cache key is not set"
        assert self._cache is not None, "Cache is not set"

        await self._cache.save(self._cache_key)

    @contextlib.asynccontextmanager
    async def _get_cache(self) -> AsyncGenerator[PushState]:
        if self._cache_key is None:
            self._cache_key = calc_cache_key(self.cfg)
        if self._cache is None:
            self._cache = await PushState.load(self._cache_key)

        try:
            yield self._cache
        finally:
            await self._save_cache()

    async def check_should_skip(self) -> None:
        if not self.cfg.wp_user_id:
            return

        cache_key = calc_cache_key(self.cfg)
        cache = await PushState.load(cache_key)

        if (
            cache.overflow is not None
            and cache.last_notification is not None
            and datetime.now() - cache.last_notification < LAZY_FETCH_INTERVAL
        ):
            logger.debug(f"用户 {self.colored} 已溢出且近期已通知，跳过获取")
            self.finish()

        if cache.credential_invalid:
            logger.debug(f"用户 {self.colored} 凭据已失效，跳过获取")
            self.finish()

    async def fetch(self) -> FetchMeResponse:
        # 获取用户信息
        logger.debug(f"正在获取 {self.colored} 的信息")
        try:
            resp = await fetch_me(self.cfg)
        except RequestFailed as e:
            logger.warning(f"获取 {self.colored} 的信息失败: {escape_tag(e.msg)}")
            if e.status_code in (500,):
                await self.push_credential_expired()
            self.finish()
        except Exception:
            logger.opt(exception=True).warning(
                f"获取 {self.colored} 的信息时发生意外错误"
            )
            self.finish()

        self._formatted_msg = resp.format_notification(self.cfg.target_droplets)
        return resp

    async def _prepare_push(self) -> tuple[Target, Bot]:
        target = self.cfg.target
        try:
            bot = await target.select()
        except Exception:
            logger.warning(f"获取 {self.colored} 的发送目标失败，跳过通知")
            self.finish()

        if self.cfg.adapter is not None and bot.type != self.cfg.adapter:
            logger.warning(f"{self.colored} 绑定的适配器不匹配，跳过通知")
            self.finish()

        return target, bot

    def _prepare_msg(self) -> UniMessage:
        return (
            UniMessage()
            if self.cfg.target.private
            else UniMessage.at(self.cfg.user_id).text("\n")
        )

    async def push(self) -> NoReturn:
        target, bot = await self._prepare_push()
        msg = self._prepare_msg().text(self._formatted_msg)

        for attempt in range(MAX_PUSH_ATTEMPT):
            try:
                await msg.send(target=target, bot=bot)
            except Exception:
                log_msg = (
                    f"向 {self.colored} 推送通知失败 "
                    f"(<y>{attempt + 1}</>/<y>{MAX_PUSH_ATTEMPT}</>)"
                )
                if attempt == MAX_PUSH_ATTEMPT - 1:
                    logger.opt(colors=True, exception=True).warning(log_msg)
                    self.finish()
                logger.warning(log_msg)
                await anyio.sleep(5)
            else:
                logger.info(f"已向 {self.colored} 推送通知")
                break

        async with self._get_cache() as cache:
            cache.last_notification = datetime.now()

        self.finish()

    async def push_credential_expired(self) -> NoReturn:
        target, bot = await self._prepare_push()
        msg = self._prepare_msg().text(
            f"用户 <c>{self.cfg.user_id}</> "
            f"[<y>{self.cfg.wp_user_name}</> #<c>{self.cfg.wp_user_id}</>] "
            "的 wplace 凭据已失效，请重新绑定"
        )

        try:
            await msg.send(target=target, bot=bot)
        except Exception:
            logger.opt(colors=True, exception=True).warning(
                f"向 {self.colored} 推送凭据失效通知失败"
            )
        else:
            logger.info(f"已向 {self.colored} 推送凭据失效通知")

        async with self._get_cache() as cache:
            cache.last_notification = datetime.now()
            cache.credential_invalid = True

        self.finish()

    async def execute(self) -> None:
        await self.check_should_skip()
        resp = await self.fetch()

        # 计算剩余时间
        remaining = resp.charges.remaining_secs()

        # 溢出状态
        if remaining <= 0:
            if self.cfg.max_overflow_notify:
                # 执行溢出通知逻辑
                await self.check_overflow()
            else:
                # 如果用户禁用了溢出通知，则直接结束
                logger.debug(f"{self.colored} 已禁用溢出通知，跳过")
            self.finish()

        async with self._get_cache() as cache:
            # 正常状态
            if cache.overflow is not None:
                # 重置溢出状态
                cache.overflow = None
                cache.overflow_notify_count = 0
                await self._save_cache()

            # 无需推送
            if remaining > self.cfg.notify_mins * 60:
                cache.last_notification = None
                logger.debug(f"{self.colored} 还剩 {remaining:.0f} 秒，跳过通知")
                self.finish()

        # 近期已通知
        if cache.last_notification is not None:
            logger.debug(f"{self.colored} 近期已通知，跳过通知")
            self.finish()

        # 执行推送
        logger.info(f"{self.colored} 剩余时间 {remaining:.0f} 秒，准备推送")
        await self.push()

    async def check_overflow(self) -> None:
        # 记录溢出开始时间
        async with self._get_cache() as cache:
            if cache.overflow is None:
                cache.overflow = datetime.now()
                cache.last_notification = None
                await self._save_cache()

            # 首次溢出通知
            if cache.last_notification is None:
                cache.overflow_notify_count = 1
                logger.info(f"{self.colored} 首次溢出，准备推送")
                await self.push()

        # 已达到最大通知次数
        if cache.overflow_notify_count >= self.cfg.max_overflow_notify:
            logger.info(
                f"{self.colored} 溢出通知已达最大次数"
                f"({self.cfg.max_overflow_notify})，跳过通知"
            )
            self.finish()

        # 溢出通知逻辑
        last_notif_delta = datetime.now() - cache.last_notification
        hours_since_overflow = (datetime.now() - cache.overflow).total_seconds() / 3600

        # 根据溢出时长确定通知频率
        if hours_since_overflow < 0.5:
            # 溢出半小时内，无需额外通知
            logger.info(f"{self.colored} 溢出未满半小时，跳过通知")
            self.finish()

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
            async with self._get_cache() as cache:
                cache.overflow_notify_count += 1
            logger.info(
                f"{self.colored} 已溢出 {hours_since_overflow:.1f} 小时，准备推送"
            )
            await self.push()


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
            await Fetcher(cfg).execute()
        except FetchDone:
            pass
        except Exception:
            logger.exception(f"处理用户 {cfg.user_id} 时发生错误")

    async with anyio.create_task_group() as tg:
        for cfg in users.load():
            tg.start_soon(wrapper, cfg, random.uniform(0, 3 * 60))
