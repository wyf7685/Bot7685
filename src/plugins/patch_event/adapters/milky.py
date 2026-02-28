import contextlib
from typing import Literal, Protocol, cast, overload, override

import nonebot
from nonebot.adapters.milky import Bot
from nonebot.adapters.milky.event import (
    Event,
    FriendMessageEvent,
    FriendNudgeEvent,
    GroupMessageReactionEvent,
    GroupMuteEvent,
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

from ..highlight import Highlight
from ..patcher import patcher

nonebot.require("nonebot_plugin_apscheduler")
from apscheduler.job import Job as SchedulerJob
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

nonebot.require("src.plugins.gtg")
from src.plugins.gtg import call_later

logger = nonebot.logger.opt(colors=True)
scheduler_job: dict[Bot, tuple[SchedulerJob, ...]] = {}
group_name_cache: dict[int, str | None] = {}
user_card_cache: dict[tuple[int, int | None], str | None] = {}


async def update_group_cache(bot: Bot) -> None:
    try:
        groups = await bot.get_group_list()
    except Exception as err:
        logger.warning(f"Failed to fetch group list: {err}")
        return

    for group in groups:
        group_name_cache[group.group_id] = group.group_name


async def update_user_cache(bot: Bot) -> None:
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
                name = data.card or data.nickname or str(user_id)
        else:
            with contextlib.suppress(ActionFailed):
                data = await bot.get_user_profile(user_id=user_id)
                name = data.nickname or str(user_id)
        user_card_cache[(user_id, group_id)] = name
        call_later(5 * 60, reset, user_id, group_id)


@nonebot.get_driver().on_bot_connect
async def on_bot_connect(bot: Bot) -> None:
    scheduler_job[bot] = (
        scheduler.add_job(
            update_group_cache,
            args=(bot,),
            trigger=CronTrigger(hour="*", minute="0"),
        ),
        scheduler.add_job(
            update_user_cache,
            args=(bot,),
            trigger=CronTrigger(second="0/15"),
        ),
    )

    async def update() -> None:
        if bot in scheduler_job:
            await update_group_cache(bot)

    call_later(5, update)


@nonebot.get_driver().on_bot_disconnect
async def on_bot_disconnect(bot: Bot) -> None:
    for job in scheduler_job.pop(bot, ()):
        with contextlib.suppress(Exception):
            job.remove()


class ModelWithScene(Protocol):
    message_scene: Literal["friend", "group", "temp"]
    sender_id: int
    peer_id: int


class H(Highlight[MessageSegment, Message]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        if segment.is_text():
            return segment.data["text"]

        shown_data = {k: v for k, v in segment.data.items() if not k.startswith("_")}
        return f"[{cls.style.le_u(segment.type)}: {cls.apply(shown_data)}]"

    @classmethod
    @override
    def message(cls, message: Message) -> str:
        return "".join(map(cls.segment, message))

    @classmethod
    @overload
    def user(cls, friend: Friend, /) -> str: ...
    @classmethod
    @overload
    def user(cls, user: int, group: int | None = None, /) -> str: ...

    @classmethod
    def user(cls, user: int | Friend, group: int | None = None) -> str:
        if isinstance(user, Friend):
            return cls.name(user.user_id, user.nickname)

        name = user_card_cache.setdefault((user, group), None)
        if name is None and (user, None) in user_card_cache:
            name = user_card_cache[(user, None)]
        return cls.name(user, name)

    @classmethod
    def group(cls, group: int | Group, /) -> str:
        name = (
            cls.name(group.group_id, group.group_name)
            if isinstance(group, Group)
            else cls.name(group, group_name_cache.get(group))
        )
        return f"[Group:{name}]"

    @classmethod
    def group_member(cls, group: Group | int, member: Member | int, /) -> str:
        name = (
            cls.name(member.user_id, member.nickname)
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
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_friend_message_event(self: FriendMessageEvent) -> str:
    return (
        f"Message {H.id(self.message_id)} from {H.source(self.data)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_message_recall_event(self: MessageRecallEvent) -> str:
    return (
        f"Message {H.id(self.data.message_seq)} "
        f"from {H.source(self.data)} "
        f"deleted by {H.user(self.data.operator_id)}"
        f"{
            f' suffix={H.style.le(self.data.display_suffix)}'
            if self.data.display_suffix
            else ''
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
        f"{'added to' if self.data.is_add else 'removed from'} "
        f"{H.id(self.data.message_seq)} "
        f"by {H.group_member(self.data.group_id, self.data.user_id)}]"
    )


@patcher
def patch_group_mute_event(self: GroupMuteEvent) -> str:
    return (
        f"{H.group_member(self.data.group_id, self.data.user_id)} "
        f"{'muted' if self.data.duration > 0 else 'unmuted'} "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
        f"{
            f' for {H.style.y(self.data.duration)} seconds'
            if self.data.duration > 0
            else ''
        }"
    )


@patcher
def patch_group_whole_mute_event(self: GroupWholeMuteEvent) -> str:
    return (
        f"{H.group(self.data.group_id)} "
        f"{'muted' if self.data.is_mute else 'unmuted'} "
        f"by {H.user(self.data.operator_id, self.data.group_id)}"
    )
