import contextlib
from typing import Literal, override

import anyio
import nonebot
from nonebot import get_driver, require
from nonebot.adapters.onebot.utils import rich_escape, truncate
from nonebot.adapters.onebot.v11 import Adapter, Bot, Event, Message, MessageSegment
from nonebot.adapters.onebot.v11.event import (
    FriendRecallNoticeEvent,
    FriendRequestEvent,
    GroupDecreaseNoticeEvent,
    GroupIncreaseNoticeEvent,
    GroupMessageEvent,
    GroupRecallNoticeEvent,
    GroupRequestEvent,
    NoticeEvent,
    NotifyEvent,
    PokeNotifyEvent,
    PrivateMessageEvent,
    Sender,
)
from nonebot.adapters.onebot.v11.exception import ActionFailed, NoLogException
from nonebot.compat import model_dump, type_validate_python
from nonebot.utils import escape_tag
from pydantic import BaseModel

require("nonebot_plugin_apscheduler")
from apscheduler.job import Job as SchedulerJob
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

require("src.plugins.gtg")
from src.plugins.gtg import call_later, call_soon

from ..highlight import Highlight
from ..patcher import patcher


class GroupInfo(BaseModel):
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int


logger = nonebot.logger.opt(colors=True)
group_info_cache: dict[int, GroupInfo] = {}
user_card_cache: dict[tuple[int, int | None], str | None] = {}
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

    await anyio.sleep(_wait_secs)

    try:
        update = type_validate_python(list[GroupInfo], await bot.get_group_list())
    except Exception as err:
        logger.warning(f"更新 {bot} 的群聊信息缓存时出错: {err!r}")
        if _try_count <= 3:
            wait_secs = 30
            call_soon(
                update_group_cache,
                bot,
                _try_count=_try_count + 1,
                _wait_secs=wait_secs,
                _id=_id,
            )
            logger.warning(f"{H.style.y(wait_secs)}s 后重试...")
        return

    logger.debug(f"更新 {bot} 的 {H.style.y(len(update))} 条群聊信息缓存")
    group_info_cache.update({info.group_id: info for info in update})
    del update_retry_id[key]


async def update_user_card_cache(bot: Bot) -> None:
    def reset(user_id: int, group_id: int | None) -> None:
        user_card_cache[(user_id, group_id)] = None

    for (user_id, group_id), name in list(user_card_cache.items()):
        if name is not None:
            continue
        if user_id == 0 or group_id == 0:
            del user_card_cache[(user_id, group_id)]
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
        call_later(5 * 60, reset, user_id, group_id)


class H(Highlight[MessageSegment, Message]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        if segment.is_text():
            return escape_tag(
                rich_escape(
                    segment.data.get("text", ""),
                    escape_comma=False,
                )
            )

        data = list(filter(lambda x: x[1] is not None, segment.data.items()))
        if not data:
            return H.style.le(f"[{H.style.u(segment.type)}]")

        def _escape(s: str) -> str:
            return escape_tag(rich_escape(truncate(str(s))))

        params = ",".join(f"{H.style.i(k, escape=True)}={_escape(v)}" for k, v in data)
        return H.style.le(f"[{H.style.u(segment.type)}:{params}]")

    @classmethod
    @override
    def message(cls, message: Message) -> str:
        return "".join(map(cls.segment, message))

    @classmethod
    def _user_card_sender(cls, sender: Sender, group: int | None) -> str:
        if sender.user_id is None:
            return H.style.c(None)

        if (name := sender.card or sender.nickname) is None:
            return cls.id(sender.user_id)

        user_card_cache[(sender.user_id, None)] = name
        if group is not None:
            user_card_cache[(sender.user_id, group)] = name

        return cls.name(sender.user_id, name)

    @classmethod
    def user(cls, user: int | Sender, group: int | None = None) -> str:
        if isinstance(user, Sender):
            return cls._user_card_sender(user, group)

        name = user_card_cache.setdefault((user, group), None)
        if name is None and (user, None) in user_card_cache:
            name = user_card_cache[(user, None)]

        return cls.name(user, name)

    @classmethod
    def group(cls, group: int) -> str:
        name = (info := group_info_cache.get(group)) and info.group_name
        return f"[Group:{cls.name(group, name)}]"


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.sender)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.sender, self.group_id)}"
        f"@{H.group(self.group_id)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_friend_recall_notice_event(self: FriendRecallNoticeEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.user_id)} "
        f"deleted"
    )


@patcher
def patch_group_recall_notice_event(self: GroupRecallNoticeEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"deleted by {H.user(self.operator_id, self.group_id)}"
    )


@patcher
def patch_notify_event(self: NotifyEvent) -> str:
    if self.sub_type == "input_status":  # napcat
        raise NoLogException
    return patch_notify_event.original(self)


def poke_napcat(self: PokeNotifyEvent, raw_info: list[dict[str, str]]) -> str:
    text = f"[{H.event_type(self)}]: "
    user = [self.user_id, self.target_id]

    if self.group_id is not None:
        text += f"{H.group(self.group_id)} "
    else:
        gen = (idx for idx, item in enumerate(raw_info) if item["type"] == "qq")
        raw_info.insert(next(gen, 0) + 1, {"type": "nor", "txt": "戳了戳"})

    for item in raw_info:
        if item["type"] == "qq":
            text += f"{H.user(user.pop(0), self.group_id)} "
        elif item["type"] == "nor":
            text += f"{item['txt']} "

    return text


def poke_lagrange(self: PokeNotifyEvent, action: str, suffix: str) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"{f'{H.group(self.group_id)} ' if self.group_id else ''}"
        f"{H.user(self.user_id, self.group_id)} {action} "
        f"{H.user(self.target_id, self.group_id)} {suffix}"
    )


@patcher
def patch_poke_notify_event(self: PokeNotifyEvent) -> str:
    data = model_dump(self)
    if raw_info := data.get("raw_info"):
        return poke_napcat(self, raw_info)
    if ((action := data.get("action")) is not None) and (
        (suffix := data.get("suffix")) is not None
    ):
        return poke_lagrange(self, action, suffix)
    return patch_poke_notify_event.original(self)


@patcher
def patch_group_decrease_notice_event(self: GroupDecreaseNoticeEvent) -> str:
    result = (
        f"[{H.event_type(self)}]: "
        f"GroupDecrease[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"by {H.user(self.operator_id, self.group_id)}"
    )
    if (key := (self.user_id, self.group_id)) in user_card_cache:
        del user_card_cache[key]
    return result


@patcher
def patch_group_increase_notice_event(self: GroupIncreaseNoticeEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"GroupIncrease[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"by {H.user(self.operator_id, self.group_id)}"
    )


@patcher
def patch_friend_request_event(self: FriendRequestEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"FriendRequest {H.user(self.user_id)} "
        f"with flag={H.id(self.flag)}"
    )


@patcher
def patch_group_request_event(self: GroupRequestEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"GroupRequest[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"with flag={H.id(self.flag)}"
    )


CUSTOM_MODELS: set[type[Event]] = set()


def custom_model[E: type[Event]](e: E) -> E:
    CUSTOM_MODELS.add(e)
    return e


@get_driver().on_startup
async def on_startup() -> None:
    Adapter.add_custom_model(*CUSTOM_MODELS)
    for e in CUSTOM_MODELS:
        logger.debug(f"Register v11 model: {H.style.g(e.__name__)}")


@custom_model
class MessageSentEvent(Event):  # NapCat
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


@custom_model
class PrivateMessageSentEvent(MessageSentEvent):  # NapCat
    message_type: Literal["private"]  # pyright: ignore[reportIncompatibleVariableOverride]

    @override
    def get_log_string(self) -> str:
        return (
            f"[{H.event_type(self)}]: "
            f"Message {H.id(self.message_id)} to "
            f"{H.user(self.target_id)} "
            f"{H.apply(self.message)}"
        )


@custom_model
class GroupMessageSentEvent(MessageSentEvent):  # NapCat
    message_type: Literal["group"]  # pyright: ignore[reportIncompatibleVariableOverride]
    group_id: int

    @override
    def get_log_string(self) -> str:
        return (
            f"[{H.event_type(self)}]: "
            f"Message {H.id(self.message_id)} "
            f"to {H.group(self.group_id)} "
            f"{H.apply(self.message)}"
        )

    @override
    def get_session_id(self) -> str:
        return f"send_group_{self.group_id}_{self.target_id}"


@custom_model
class ReactionNoticeEvent(NoticeEvent):  # Lagrange
    notice_type: Literal["reaction"]  # pyright: ignore[reportIncompatibleVariableOverride]
    sub_type: str
    group_id: int
    message_id: int
    operator_id: int
    code: str
    count: int

    @override
    def get_event_name(self) -> str:
        return f"notice.reaction.{self.sub_type}"

    @override
    def get_session_id(self) -> str:
        return f"reaction_{self.group_id}_{self.operator_id}"


@custom_model
class ReactionAddNoticeEvent(ReactionNoticeEvent):  # Lagrange
    sub_type: Literal["add"]  # pyright: ignore[reportIncompatibleVariableOverride]

    @override
    def get_log_string(self) -> str:
        return (
            f"[{H.event_type(self)}]: "
            f"Reaction {H.style.y(self.code)} "
            f"added to {H.id(self.message_id)} "
            f"(current {H.style.y(self.count)}) "
            f"by {H.user(self.operator_id, self.group_id)}"
            f"@{H.group(self.group_id)}"
        )


@custom_model
class ReactionRemoveNoticeEvent(ReactionNoticeEvent):  # Lagrange
    sub_type: Literal["remove"]  # pyright: ignore[reportIncompatibleVariableOverride]

    @override
    def get_log_string(self) -> str:
        return (
            f"[{H.event_type(self)}]: "
            f"Reaction {H.style.y(self.code)} "
            f"removed from {H.id(self.message_id)} "
            f"(current {H.style.y(self.count)}) "
            f"by {H.user(self.operator_id, self.group_id)}"
            f"@{H.group(self.group_id)}"
        )


scheduler_job: dict[Bot, tuple[SchedulerJob, ...]] = {}


@get_driver().on_bot_connect
async def on_bot_connect(bot: Bot) -> None:
    scheduler_job[bot] = (
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
    )

    async def update() -> None:
        if bot in scheduler_job:
            await update_group_cache(bot)

    call_later(5, update)


@get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot) -> None:
    for job in scheduler_job.pop(bot, []):
        with contextlib.suppress(Exception):
            job.remove()
