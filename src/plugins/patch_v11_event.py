import asyncio
from typing import override

from nonebot import get_driver, require
from nonebot.adapters.onebot.utils import highlight_rich_message
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.log import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel
from nonebot.compat import type_validate_python

require("nonebot_plugin_apscheduler")
from apscheduler.job import Job as SchedulerJob
from nonebot_plugin_apscheduler import scheduler


class GroupInfo(BaseModel):
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int


logger = logger.opt(colors=True)
group_info_cache: dict[int, GroupInfo] = {}
scheduler_job: dict[Bot, SchedulerJob] = {}
update_retry_id: dict[str, int] = {}


async def update_group_cache(
    bot: Bot,
    *,
    _try_count: int = 1,
    _wait_secs: int = 0,
    _id: int = 0,
):
    key = repr(bot)
    if _id == 0:
        if key in update_retry_id:
            return
        _id = hash(f"{key}{id(bot)}")
        update_retry_id[key] = _id
    elif update_retry_id.get(key, 0) != _id:
        return

    await asyncio.sleep(_wait_secs)

    try:
        update = {
            (info := type_validate_python(GroupInfo, item)).group_id: info
            for item in await bot.get_group_list()
        }
    except Exception as err:
        logger.warning(f"更新 {bot} 的群聊信息缓存时出错: {err!r}")
        if _try_count <= 3:
            coro = update_group_cache(
                bot, _try_count=_try_count + 1, _wait_secs=30, _id=_id
            )
            asyncio.get_running_loop().create_task(coro)
            logger.warning("<y>30</y>s 后重试...")
        return

    logger.success(f"更新 {bot} 的 <y>{len(update)}</y> 条群聊信息缓存")
    group_info_cache.update(update)
    del update_retry_id[key]


def patch_private():
    @override
    def get_event_description(self: PrivateMessageEvent) -> str:
        sender = (
            f"<y>{escape_tag(name)}</y>(<c>{self.user_id}</c>)"
            if (name := (self.sender.card or self.sender.nickname))
            else f"<c>{self.user_id}</c>"
        )
        return (
            f"Message <c>{self.message_id}</c> from {sender} "
            f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
        )

    PrivateMessageEvent.get_event_description = get_event_description
    logger.success("Patched <g>PrivateMessageEvent</g>.<y>get_event_description</y>")


def patch_group():
    @override
    def get_event_description(self: GroupMessageEvent) -> str:
        sender = (
            f"<y>{escape_tag(name)}</y>(<c>{self.user_id}</c>)"
            if (name := (self.sender.card or self.sender.nickname))
            else f"<c>{self.user_id}</c>"
        )
        group = (
            f"<y>{escape_tag(info.group_name)}</y>(<c>{self.group_id}</c>)"
            if (info := group_info_cache.get(self.group_id))
            else f"<c>{self.group_id}</c>"
        )
        return (
            f"Message <c>{self.message_id}</c> from [群:{group}]@{sender} "
            f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
        )

    GroupMessageEvent.get_event_description = get_event_description
    logger.success("Patched <g>GroupMessageEvent</g>.<y>get_event_description</y>")


@get_driver().on_startup
def on_startup():
    patch_private()
    patch_group()


@get_driver().on_bot_connect
async def on_bot_connect(bot: Bot):
    await update_group_cache(bot)

    async def job():
        await update_group_cache(bot)

    scheduler_job[bot] = scheduler.add_job(job, trigger="cron", hour="*", minute="0")


@get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot):
    if bot in scheduler_job:
        scheduler_job.pop(bot).remove()
