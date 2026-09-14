import asyncio
import contextlib
from typing import Literal, Protocol, cast, overload, override

import nonebot
from expiringdictx import ExpiringDict
from nonebot.adapters.milky import Bot
from nonebot.adapters.milky.event import (
    Event,
    FriendMessageEvent,
    FriendNudgeEvent,
    GroupDisbandEvent,
    GroupMessageReactionEvent,
    GroupMuteEvent,
    GroupNameChangeEvent,
    GroupNudgeEvent,
    GroupWholeMuteEvent,
    MessageEvent,
    MessageRecallEvent,
)
from nonebot.adapters.milky.exception import ActionFailed
from nonebot.adapters.milky.message import Message, MessageSegment
from nonebot.adapters.milky.model.base import ModelBase
from nonebot.adapters.milky.model.common import Friend, Group, Member
from nonebot.adapters.milky.model.message import IncomingMessage
from nonebot.message import event_preprocessor
from nonebot.utils import escape_tag

from src.highlight import Highlight

from ..patcher import patcher

USER_CARD_CACHE_CAPACITY = 10_000
USER_CARD_CACHE_TTL = 5 * 60

logger = nonebot.logger.opt(colors=True)
connected_bots: set[Bot] = set()
cache_refresh_event = asyncio.Event()
cache_refresh_task: asyncio.Task[None] | None = None
user_cache_refresh_requested = False
pending_group_ids: set[int] = set()
pending_group_snapshots: set[Bot] = set()
group_name_cache: dict[int, str] = {}
user_card_cache: ExpiringDict[tuple[int, int | None], str | None] = ExpiringDict(
    capacity=USER_CARD_CACHE_CAPACITY,
    default_age=USER_CARD_CACHE_TTL,
)


async def update_group_cache(bot: Bot) -> None:
    try:
        groups = await bot.get_group_list()
    except Exception as err:
        logger.warning(f"Failed to fetch group list: {err}")
        return

    for group in groups:
        group_name_cache[group.group_id] = group.group_name


async def update_group_cache_entries(bot: Bot, group_ids: set[int]) -> set[int]:
    async def update(group_id: int) -> int | None:
        try:
            group = await bot.get_group_info(group_id=group_id)
        except ActionFailed:
            return None

        group_name_cache[group.group_id] = group.group_name
        return group_id

    return {
        group_id
        for group_id in await asyncio.gather(
            *(update(group_id) for group_id in group_ids)
        )
        if group_id is not None
    }


async def update_user_cache(bot: Bot) -> None:
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
                name = data.card or data.nickname or str(user_id)
        else:
            with contextlib.suppress(ActionFailed):
                data = await bot.get_user_profile(user_id=user_id)
                name = data.nickname or str(user_id)

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
                    await update_user_cache(bot)
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
            name="milky-cache-refresh",
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


@event_preprocessor
async def update_group_cache_from_event(
    event: GroupNameChangeEvent | GroupDisbandEvent,
) -> None:
    if isinstance(event, GroupNameChangeEvent):
        group_name_cache[event.data.group_id] = event.data.new_group_name
        pending_group_ids.discard(event.data.group_id)
    elif isinstance(event, GroupDisbandEvent):
        group_name_cache.pop(event.data.group_id, None)
        pending_group_ids.discard(event.data.group_id)


class ModelWithScene(Protocol):
    message_scene: Literal["friend", "group", "temp"]
    sender_id: int
    peer_id: int


@patcher.bind
class H(Highlight[MessageSegment, Message]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        if segment.is_text():
            return escape_tag(segment.data["text"])

        shown_data = {k: v for k, v in segment.data.items() if not k.startswith("_")}
        return f"[{cls.style.le_u(segment.type)}: {cls.apply(shown_data)}]"

    @classmethod
    @override
    def message(cls, message: Message) -> str:
        return "".join(map(cls.segment, message))

    @overload
    @classmethod
    def user(cls, friend: Friend, /) -> str: ...
    @overload
    @classmethod
    def user(cls, user: int, group: int | None = None, /) -> str: ...

    @classmethod
    def user(cls, user: int | Friend, group: int | None = None) -> str:
        if isinstance(user, Friend):
            return cls.name(user.user_id, user.nickname)

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
    def group(cls, group: int | Group, /) -> str:
        if isinstance(group, Group):
            group_id = group.group_id
            name = group.group_name
            group_name_cache[group_id] = name
            pending_group_ids.discard(group_id)
        else:
            group_id = group
            name = group_name_cache.get(group_id)
            if name is None:
                request_group_cache_refresh(group_id)

        return f"[Group:{cls.name(group_id, name)}]"

    @classmethod
    def group_member(cls, group: Group | int, member: Member | int, /) -> str:
        name = (
            cls.name(member.user_id, member.card or member.nickname)
            if isinstance(member, Member)
            else cls.user(member, group.group_id if isinstance(group, Group) else group)
        )
        return f"{name}@{cls.group(group)}"

    @classmethod
    def source(cls, data: ModelWithScene) -> str:
        match cast("ModelBase", data):
            # https://milky.ntqqrev.org/struct/IncomingMessage#type-friend
            case IncomingMessage(
                message_scene="friend",
                friend=friend,
                sender_id=sender_id,
            ):
                return cls.user(friend) if friend is not None else cls.user(sender_id)
            # https://milky.ntqqrev.org/struct/IncomingMessage#type-group
            case IncomingMessage(
                message_scene="group",
                group=group,
                group_member=member,
                peer_id=peer_id,
                sender_id=sender_id,
            ):
                return (
                    cls.group_member(group, member)
                    if group and member
                    else cls.group_member(peer_id, sender_id)
                )
            # https://milky.ntqqrev.org/struct/IncomingMessage#type-temp
            case IncomingMessage(
                message_scene="temp",
                group=group,
                sender_id=sender_id,
            ):
                return (
                    f"{cls.user(sender_id, group.group_id)}@[Temp:{cls.group(group)}]"
                    if group
                    else cls.user(sender_id)
                )
            # Common ModelBase with message_scene
            case ModelBase(
                message_scene=scene,
                peer_id=peer_id,
                sender_id=sender_id,
            ):
                return (
                    f"{cls.user(sender_id, peer_id)}@{cls.group(peer_id)}"
                    if scene == "group"
                    else cls.user(sender_id)
                )
            # Fallback
            case _:
                return cls.id(data.sender_id)


@patcher
def patch_event(self: Event) -> str:
    return (
        H.apply(self)
        if type(self).get_event_description is Event.get_event_description
        else self.get_event_description()
    )


@patcher
def patch_message_event(self: MessageEvent) -> str:
    return (
        f"Message {H.id(self.message_id)} from {H.source(self.data)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_friend_message_event(self: FriendMessageEvent) -> str:
    return (
        f"Message {H.id(self.message_id)} from {H.source(self.data)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_message_recall_event(self: MessageRecallEvent) -> str:
    return (
        f"Message {H.id(self.data.message_seq)} "
        f"from {H.source(self.data)} "
        f"deleted by {H.user(self.data.operator_id)}"
        f"{
            f" suffix={H.style.le(self.data.display_suffix)}"
            if self.data.display_suffix
            else ""
        }"
    )


def _nudge_action(action: str, img_url: str, /) -> str:
    return f"{action}[{H.style.i_c(img_url)}]" if img_url else action


@patcher
def patch_friend_nudge_event(self: FriendNudgeEvent) -> str:
    return (
        f"{H.user(self.self_id if self.data.is_self_send else self.data.user_id)} "
        f"{_nudge_action(self.data.display_action, self.data.display_action_img_url)} "
        f"{H.user(self.self_id if self.data.is_self_receive else self.data.user_id)} "
        f"{self.data.display_suffix}"
    )


@patcher
def patch_group_name_change_event(self: GroupNameChangeEvent) -> str:
    return (
        f"{H.group(self.data.group_id)} renamed to "
        f"{H.style.y(self.data.new_group_name, escape=True)} "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
    )


@patcher
def patch_group_disband_event(self: GroupDisbandEvent) -> str:
    return (
        f"{H.group(self.data.group_id)} disbanded "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
    )


@patcher
def patch_group_nudge_event(self: GroupNudgeEvent) -> str:
    return (
        f"{H.group(self.data.group_id)}: "
        f"{H.user(self.data.sender_id, self.data.group_id)} "
        f"{_nudge_action(self.data.display_action, self.data.display_action_img_url)} "
        f"{H.user(self.data.receiver_id, self.data.group_id)} "
        f"{self.data.display_suffix}"
    )


@patcher
def patch_group_message_reaction_event(self: GroupMessageReactionEvent) -> str:
    return (
        f"Reaction {H.style.y(self.data.face_id)} "
        f"{"added to" if self.data.is_add else "removed from"} "
        f"{H.id(self.data.message_seq)} "
        f"by {H.group_member(self.data.group_id, self.data.user_id)}]"
    )


@patcher
def patch_group_mute_event(self: GroupMuteEvent) -> str:
    return (
        f"{H.group_member(self.data.group_id, self.data.user_id)} "
        f"{"muted" if self.data.duration > 0 else "unmuted"} "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
        f"{
            f" for {H.style.y(self.data.duration)} seconds"
            if self.data.duration > 0
            else ""
        }"
    )


@patcher
def patch_group_whole_mute_event(self: GroupWholeMuteEvent) -> str:
    return (
        f"{H.group(self.data.group_id)} "
        f"{"muted" if self.data.is_mute else "unmuted"} "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
    )
