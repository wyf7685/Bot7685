import asyncio
import contextlib
from typing import Literal, override

import nonebot
from expiringdictx import ExpiringDict
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

from src.highlight import Highlight

from ..patcher import patcher


class GroupInfo(BaseModel):
    group_id: int
    group_name: str
    member_count: int
    max_member_count: int


GROUP_NAME_CACHE_CAPACITY = 10_000
GROUP_NAME_CACHE_TTL = 60 * 60
USER_CARD_CACHE_CAPACITY = 10_000
USER_CARD_CACHE_TTL = 5 * 60

logger = nonebot.logger.opt(colors=True)
connected_bots: set[Bot] = set()
cache_refresh_event = asyncio.Event()
cache_refresh_task: asyncio.Task[None] | None = None
user_cache_refresh_requested = False
pending_group_ids: set[int] = set()
pending_group_snapshots: set[Bot] = set()
group_name_cache: ExpiringDict[int, str] = ExpiringDict(
    capacity=GROUP_NAME_CACHE_CAPACITY,
    default_age=GROUP_NAME_CACHE_TTL,
)
user_card_cache: ExpiringDict[tuple[int, int | None], str | None] = ExpiringDict(
    capacity=USER_CARD_CACHE_CAPACITY,
    default_age=USER_CARD_CACHE_TTL,
)


async def update_group_cache(bot: Bot) -> None:
    try:
        groups = type_validate_python(list[GroupInfo], await bot.get_group_list())
    except Exception as err:
        logger.warning(
            f"Failed to fetch group list with <c>{escape_tag(repr(bot))}</>: "
            f"<r>{escape_tag(repr(err))}</>"
        )
        return

    logger.debug(
        f"Updated {H.style.y(len(groups))} group cache entries with "
        f"<c>{escape_tag(repr(bot))}</>"
    )
    for group in groups:
        group_name_cache.set(group.group_id, group.group_name)


async def update_group_cache_entries(bot: Bot, group_ids: set[int]) -> set[int]:
    async def update(group_id: int) -> int | None:
        try:
            data = await bot.get_group_info(group_id=group_id, no_cache=True)
        except ActionFailed:
            return None

        group = type_validate_python(GroupInfo, data)
        group_name_cache.set(group.group_id, group.group_name)
        return group_id

    return {
        group_id
        for group_id in await asyncio.gather(
            *(update(group_id) for group_id in group_ids)
        )
        if group_id is not None
    }


async def update_user_card_cache(bot: Bot) -> None:
    async def update(user_id: int, group_id: int | None) -> None:
        if user_id == 0 or group_id == 0:
            user_card_cache.pop((user_id, group_id), None)
            return

        name = None
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

        if name is not None:
            user_card_cache.set((user_id, group_id), name)

    coros = [
        update(user_id, group_id)
        for (user_id, group_id), name in user_card_cache.items()
        if name is None
    ]
    await asyncio.gather(*coros)


def request_user_cache_refresh() -> None:
    global user_cache_refresh_requested

    user_cache_refresh_requested = True
    cache_refresh_event.set()


def request_group_cache_refresh(group_id: int) -> None:
    if group_id == 0:
        return
    pending_group_ids.add(group_id)
    cache_refresh_event.set()


def request_group_cache_snapshot(bot: Bot) -> None:
    pending_group_snapshots.add(bot)
    cache_refresh_event.set()


async def run_cache_refresh() -> None:
    global user_cache_refresh_requested

    while True:
        await cache_refresh_event.wait()
        cache_refresh_event.clear()

        refresh_users = user_cache_refresh_requested
        user_cache_refresh_requested = False
        group_ids = set(pending_group_ids)
        pending_group_ids.difference_update(group_ids)
        snapshot_bots = set(pending_group_snapshots)
        pending_group_snapshots.difference_update(snapshot_bots)

        for bot in snapshot_bots:
            if bot in connected_bots:
                await update_group_cache(bot)

        remaining_group_ids = {
            group_id for group_id in group_ids if group_id not in group_name_cache
        }
        for bot in tuple(connected_bots):
            if not remaining_group_ids:
                break
            try:
                resolved = await update_group_cache_entries(bot, remaining_group_ids)
            except Exception as err:
                logger.warning(
                    f"Failed to refresh group cache with "
                    f"<c>{escape_tag(repr(bot))}</>: "
                    f"<r>{escape_tag(repr(err))}</>"
                )
            else:
                remaining_group_ids.difference_update(resolved)

        pending_group_ids.update(
            group_id
            for group_id in remaining_group_ids
            if group_id not in group_name_cache
        )

        if refresh_users:
            for bot in tuple(connected_bots):
                try:
                    await update_user_card_cache(bot)
                except Exception as err:
                    logger.warning(
                        f"Failed to refresh user cache with "
                        f"<c>{escape_tag(repr(bot))}</>: "
                        f"<r>{escape_tag(repr(err))}</>"
                    )


@nonebot.get_driver().on_bot_connect
async def on_bot_connect(bot: Bot) -> None:
    global cache_refresh_task

    connected_bots.add(bot)
    if cache_refresh_task is None:
        cache_refresh_task = asyncio.create_task(
            run_cache_refresh(),
            name="onebot-v11-cache-refresh",
        )
    request_user_cache_refresh()
    request_group_cache_snapshot(bot)
    await asyncio.sleep(0)


@nonebot.get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot) -> None:
    global cache_refresh_task

    connected_bots.discard(bot)
    pending_group_snapshots.discard(bot)
    if connected_bots:
        cache_refresh_event.set()
        return

    task = cache_refresh_task
    cache_refresh_task = None
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@patcher.bind
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

        user_card_cache.set((sender.user_id, None), name)
        if group is not None:
            user_card_cache.set((sender.user_id, group), name)

        return cls.name(sender.user_id, name)

    @classmethod
    def user(cls, user: int | Sender, group: int | None = None) -> str:
        if isinstance(user, Sender):
            return cls._user_card_sender(user, group)

        key = (user, group)
        try:
            name = user_card_cache[key]
        except KeyError:
            user_card_cache.set(key, None)
            name = None
        if name is None:
            request_user_cache_refresh()
            name = user_card_cache.get((user, None))

        return cls.name(user, name)

    @classmethod
    def group(cls, group: int) -> str:
        name = group_name_cache.get(group)
        if name is None:
            request_group_cache_refresh(group)
        return f"[Group:{cls.name(group, name)}]"


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    return (
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.sender)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    return (
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.sender, self.group_id)}"
        f"@{H.group(self.group_id)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_friend_recall_notice_event(self: FriendRecallNoticeEvent) -> str:
    return f"Message {H.id(self.message_id)} from {H.user(self.user_id)} deleted"


@patcher
def patch_group_recall_notice_event(self: GroupRecallNoticeEvent) -> str:
    return (
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
    text = ""
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
            text += f"{item["txt"]} "

    return text


def poke_lagrange(self: PokeNotifyEvent, action: str, suffix: str) -> str:
    return (
        f"{f"{H.group(self.group_id)} " if self.group_id else ""}"
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
        f"GroupDecrease[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"by {H.user(self.operator_id, self.group_id)}"
    )
    user_card_cache.pop((self.user_id, self.group_id), None)
    return result


@patcher
def patch_group_increase_notice_event(self: GroupIncreaseNoticeEvent) -> str:
    return (
        f"GroupIncrease[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"by {H.user(self.operator_id, self.group_id)}"
    )


@patcher
def patch_friend_request_event(self: FriendRequestEvent) -> str:
    return f"FriendRequest {H.user(self.user_id)} with flag={H.id(self.flag)}"


@patcher
def patch_group_request_event(self: GroupRequestEvent) -> str:
    return (
        f"GroupRequest[{self.sub_type}] "
        f"{H.user(self.user_id, self.group_id)}"
        f"@{H.group(self.group_id)} "
        f"with flag={H.id(self.flag)}"
    )


CUSTOM_MODELS: set[type[Event]] = set()


def custom_model[E: type[Event]](e: E) -> E:
    CUSTOM_MODELS.add(e)
    return e


@nonebot.get_driver().on_startup
async def register_custom_models() -> None:
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
            f"Reaction {H.style.y(self.code)} "
            f"removed from {H.id(self.message_id)} "
            f"(current {H.style.y(self.count)}) "
            f"by {H.user(self.operator_id, self.group_id)}"
            f"@{H.group(self.group_id)}"
        )
