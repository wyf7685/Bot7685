import asyncio
from collections.abc import Callable
import contextlib
import functools
from typing import override

from nonebot import get_driver, require
from nonebot.adapters.onebot.utils import highlight_rich_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    NotifyEvent,
    PokeNotifyEvent,
    PrivateMessageEvent,
)
from nonebot.compat import type_validate_python
from nonebot.exception import ActionFailed, NoLogException
from nonebot.log import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel

require("nonebot_plugin_apscheduler")
from apscheduler.job import Job as SchedulerJob
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler


class GroupInfo(BaseModel):
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int


logger = logger.opt(colors=True)
group_info_cache: dict[int, GroupInfo] = {}
user_card_cache: dict[tuple[int, int | None], str | None] = {}
scheduler_job: dict[Bot, list[SchedulerJob]] = {}
update_retry_id: dict[str, int] = {}
undo_call: dict[tuple[type, Callable], Callable[[], None]] = {}


async def update_group_cache(
    bot: Bot,
    *,
    _try_count: int = 1,
    _wait_secs: int = 0,
    _id: int = 0,
) -> None:
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
                bot,
                _try_count=_try_count + 1,
                _wait_secs=30,
                _id=_id,
            )
            asyncio.get_running_loop().create_task(coro)
            logger.warning("<y>30</y>s 后重试...")
        return

    logger.success(f"更新 {bot} 的 <y>{len(update)}</y> 条群聊信息缓存")
    group_info_cache.update(update)
    del update_retry_id[key]


async def update_user_card_cache(bot: Bot) -> None:
    for (user_id, group_id), name in list(user_card_cache.items()):
        if name is not None:
            continue
        if group_id is not None:
            with contextlib.suppress(ActionFailed):
                data = await bot.get_group_member_info(
                    group_id=group_id, user_id=user_id
                )
                name = data.get("card") or data.get("nickname") or str(user_id)
        else:
            with contextlib.suppress(ActionFailed):
                data = await bot.get_stranger_info(user_id=user_id)
                name = data.get("nickname") or str(user_id)
        user_card_cache[(user_id, group_id)] = name


type Patcher = Callable[[], Callable[[], None]]
type PatcherFunc[**P, R] = Callable[[Callable[P, R]], Callable[P, R]]


def patch[**P, R](
    Class: type, original: Callable[P, R]
) -> Callable[[PatcherFunc[P, R]], Patcher]:
    def decorator(patcher_func: PatcherFunc[P, R]) -> Patcher:
        name = original.__name__
        patcher = functools.wraps(original)(patcher_func(original))

        def undo() -> None:
            if undo_call.pop((Class, original), None) is not None:
                setattr(Class, name, original)

        def patch() -> Callable[[], None]:
            setattr(Class, name, override(patcher))
            logger.success(f"patched <g>{Class.__name__}</g>.<y>{name}</y>")
            return undo

        undo_call[(Class, original)] = undo
        return patch

    return decorator


@patch(PrivateMessageEvent, PrivateMessageEvent.get_event_description)
def patch_private(_):
    def patcher(self: PrivateMessageEvent) -> str:
        sender = (
            f"<y>{escape_tag(name)}</y>(<c>{self.user_id}</c>)"
            if (name := (self.sender.card or self.sender.nickname))
            else f"<c>{self.user_id}</c>"
        )
        return (
            f"Message <c>{self.message_id}</c> from {sender} "
            f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
        )

    return patcher


@patch(GroupMessageEvent, GroupMessageEvent.get_event_description)
def patch_group(_):
    def patcher(self: GroupMessageEvent) -> str:
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

    return patcher


@patch(NotifyEvent, NotifyEvent.get_log_string)
def patch_input_status(original: Callable[[NotifyEvent], str]):
    def patcher(self: NotifyEvent) -> str:
        if self.sub_type == "input_status":
            raise NoLogException("OneBot V11")
        return original(self)

    return patcher


@patch(PokeNotifyEvent, PokeNotifyEvent.get_event_description)
def patch_poke(original: Callable[[PokeNotifyEvent], str]):
    def patcher(self: PokeNotifyEvent) -> str:
        raw_info: list = self.model_dump().get("raw_info", [])
        if not raw_info:
            return original(self)

        text = ""
        user = [self.user_id, self.target_id]

        if self.group_id is not None:
            text += (
                f"[群:<y>{escape_tag(info.group_name)}</y>(<c>{self.group_id}</c>)] "
                if (info := group_info_cache.get(self.group_id))
                else f"[群:<c>{self.group_id}</c>] "
            )
        else:
            gen = (idx + 1 for idx, item in enumerate(raw_info) if item["type"] == "qq")
            raw_info.insert(next(gen, 1), {"type": "nor", "txt": "戳了戳"})

        for item in raw_info:
            if item["type"] == "qq":
                user_id = user.pop(0)
                name = user_card_cache.setdefault((user_id, self.group_id), None)
                text += (
                    f"<y>{escape_tag(name)}</y>(<c>{user_id}</c>) "
                    if name is not None
                    else f"<c>{user_id}</c> "
                )
            elif item["type"] == "nor":
                text += f"{item['txt']} "

        return text

    return patcher


@get_driver().on_startup
def on_startup() -> None:
    patch_private()
    patch_group()
    patch_input_status()
    patch_poke()


@get_driver().on_bot_connect
async def on_bot_connect(bot: Bot) -> None:
    scheduler_job[bot] = [
        scheduler.add_job(
            update_group_cache,
            args=(bot,),
            trigger=CronTrigger(hour="*", minute="0"),
        ),
        scheduler.add_job(
            update_user_card_cache,
            args=(bot,),
            trigger=CronTrigger(second="0/15"),
        ),
    ]

    async def update():
        await asyncio.sleep(5)
        if bot in scheduler_job:
            await update_group_cache(bot)

    asyncio.create_task(update()).add_done_callback(lambda _: None)


@get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot) -> None:
    for job in scheduler_job.pop(bot, []):
        job.remove()
