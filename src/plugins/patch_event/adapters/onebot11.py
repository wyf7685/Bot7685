import asyncio
import contextlib
from typing import Literal, override

from nonebot import get_driver, require
from nonebot.compat import type_validate_python
from nonebot.exception import ActionFailed, NoLogException
from nonebot.log import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel

require("nonebot_plugin_apscheduler")
from apscheduler.job import Job as SchedulerJob
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

from ..patcher import Patcher

with contextlib.suppress(ImportError):
    from nonebot.adapters.onebot.utils import highlight_rich_message
    from nonebot.adapters.onebot.v11 import Adapter, Bot, Message
    from nonebot.adapters.onebot.v11.event import (
        Event,
        FriendRecallNoticeEvent,
        GroupMessageEvent,
        GroupRecallNoticeEvent,
        NotifyEvent,
        PokeNotifyEvent,
        PrivateMessageEvent,
        Sender,
    )

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

        logger.debug(f"更新 {bot} 的 <y>{len(update)}</y> 条群聊信息缓存")
        group_info_cache.update(update)
        del update_retry_id[key]

    async def update_user_card_cache(bot: Bot) -> None:
        loop = asyncio.get_event_loop()

        def reset(user_id: int, group_id: int | None) -> None:
            user_card_cache[(user_id, group_id)] = None

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
            loop.call_later(5 * 60, reset, user_id, group_id)

    def colored_user_card(user_id: int, group_id: int | None = None) -> str:
        name = user_card_cache.setdefault((user_id, group_id), None)
        return (
            f"<y>{escape_tag(name)}</y>(<c>{user_id}</c>)"
            if name is not None
            else f"<c>{user_id}</c>"
        )

    @Patcher
    class PatchPrivateMessageEvent(PrivateMessageEvent):
        @override
        def get_log_string(self) -> str:
            sender = (
                f"<y>{escape_tag(name)}</y>(<c>{self.user_id}</c>)"
                if (name := (self.sender.card or self.sender.nickname))
                else f"<c>{self.user_id}</c>"
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> from {sender} "
                f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
            )

    @Patcher
    class PatchGroupMessageEvent(GroupMessageEvent):
        @override
        def get_log_string(self) -> str:
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
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> from {sender}@[Group:{group}] "
                f"{''.join(highlight_rich_message(repr(self.original_message.to_rich_text())))}"
            )

    @Patcher
    class PatchFriendRecallNoticeEvent(FriendRecallNoticeEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> from "
                f"{colored_user_card(self.user_id)} deleted"
            )

    @Patcher
    class PatchGroupRecallNoticeEvent(GroupRecallNoticeEvent):
        @override
        def get_log_string(self) -> str:
            group = (
                f"<y>{escape_tag(info.group_name)}</y>(<c>{self.group_id}</c>)"
                if (info := group_info_cache.get(self.group_id))
                else f"<c>{self.group_id}</c>"
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> from "
                f"{colored_user_card(self.user_id, self.group_id)}@[Group:{group}] "
                f"deleted by {colored_user_card(self.operator_id, self.group_id)}"
            )

    @Patcher
    class PatchNotifyEvent(NotifyEvent):
        @override
        def get_log_string(self) -> str:
            if self.sub_type == "input_status":
                raise NoLogException("OneBot V11")
            return PatchNotifyEvent.origin.get_log_string(self)

    @Patcher
    class PatchPokeNotifyEvent(PokeNotifyEvent):
        @override
        def get_log_string(self) -> str:
            raw_info: list = self.model_dump().get("raw_info", [])
            if not raw_info:
                return PatchPokeNotifyEvent.origin.get_log_string(self)

            text = f"[{self.get_event_name()}]: "
            user = [self.user_id, self.target_id]

            if self.group_id is not None:
                text += (
                    (
                        f"[Group:<y>{escape_tag(info.group_name)}</y>"
                        f"(<c>{self.group_id}</c>)] "
                    )
                    if (info := group_info_cache.get(self.group_id))
                    else f"[Group:<c>{self.group_id}</c>] "
                )
            else:
                gen = (
                    idx + 1 for idx, item in enumerate(raw_info) if item["type"] == "qq"
                )
                raw_info.insert(next(gen, 1), {"type": "nor", "txt": "戳了戳"})

            for item in raw_info:
                if item["type"] == "qq":
                    text += colored_user_card(user.pop(0), self.group_id) + " "
                elif item["type"] == "nor":
                    text += f"{item['txt']} "

            return text

    class MessageSentEvent(Event):
        post_type: Literal["message_sent"]  # pyright: ignore[reportIncompatibleVariableOverride]
        message_type: str
        sub_type: str
        message_sent_type: str
        message_id: int
        user_id: int  # self_id
        sender: Sender
        message: Message
        raw_message: str
        font: int
        target_id: int

        @override
        def get_event_name(self) -> str:
            return f"{self.post_type}.{self.message_type}.{self.sub_type}"

        @override
        def get_message(self) -> Message:
            return self.message

        @override
        def get_session_id(self) -> str:
            return f"send_{self.target_id}"

    class PrivateMessageSentEvent(MessageSentEvent):
        message_type: Literal["private"]  # pyright: ignore[reportIncompatibleVariableOverride]

        @override
        def get_log_string(self) -> str:
            user = (
                f"<y>{escape_tag(name)}</y>(<c>{self.target_id}</c>)"
                if (name := user_card_cache.setdefault((self.target_id, None), None))
                else f"<c>{self.target_id}</c>"
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> to {user} "
                f"{''.join(highlight_rich_message(repr(self.message.to_rich_text())))}"
            )

    class GroupMessageSentEvent(MessageSentEvent):
        message_type: Literal["group"]  # pyright: ignore[reportIncompatibleVariableOverride]
        group_id: int

        @override
        def get_log_string(self) -> str:
            group = (
                f"<y>{escape_tag(name.group_name)}</y>(<c>{self.group_id}</c>)"
                if (name := group_info_cache.get(self.group_id))
                else f"<c>{self.group_id}</c>"
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> to [Group:{group}] "
                f"{''.join(highlight_rich_message(repr(self.message.to_rich_text())))}"
            )

        @override
        def get_session_id(self) -> str:
            return f"send_group_{self.group_id}_{self.target_id}"

    @get_driver().on_startup
    async def on_startup() -> None:
        for e in {MessageSentEvent, PrivateMessageSentEvent, GroupMessageSentEvent}:
            Adapter.add_custom_model(e)
            logger.success(f"Register v11 model: <g>{e.__name__}</g>")

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

        async def update() -> None:
            await asyncio.sleep(5)
            if bot in scheduler_job:
                await update_group_cache(bot)

        asyncio.create_task(update())  # noqa: RUF006

    @get_driver().on_bot_disconnect
    async def on_bot_disconnect(bot: Bot) -> None:
        for job in scheduler_job.pop(bot, []):
            job.remove()
