from typing import Literal, Protocol, cast, override

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
from nonebot.adapters.milky.message import Message, MessageSegment
from nonebot.adapters.milky.model.base import ModelBase
from nonebot.adapters.milky.model.common import Friend, Group, Member
from nonebot.adapters.milky.model.message import IncomingMessage

from ..highlight import Highlight
from ..patcher import patcher


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
    def friend(cls, friend: Friend) -> str:
        return cls.name(friend.user_id, friend.nickname)

    @classmethod
    def group(cls, group: Group) -> str:
        return cls.name(group.group_id, group.group_name)

    @classmethod
    def member(cls, member: Member) -> str:
        return cls.name(member.user_id, member.nickname)

    @classmethod
    def group_member(cls, group: Group, member: Member) -> str:
        return f"{cls.member(member)}@[Group:{cls.group(group)}]"

    @classmethod
    def group_member_id(cls, group_id: int, user_id: int) -> str:
        return f"{cls.id(user_id)}@[Group:{cls.id(group_id)}]"

    @classmethod
    def source(cls, data: ModelWithScene) -> str:
        match cast("ModelBase", data):
            # https://milky.ntqqrev.org/struct/IncomingMessage#type-friend
            case IncomingMessage(
                message_scene="friend",
                friend=friend,
                sender_id=sender_id,
            ):
                return cls.friend(friend) if friend else cls.id(sender_id)
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
                    else cls.group_member_id(peer_id, sender_id)
                )
            # https://milky.ntqqrev.org/struct/IncomingMessage#type-temp
            case IncomingMessage(
                message_scene="temp",
                group=group,
                sender_id=sender_id,
            ):
                return (
                    f"{cls.id(sender_id)}@[Temp:{cls.group(group)}]"
                    if group
                    else cls.id(sender_id)
                )
            # Common ModelBase with message_scene
            case ModelBase(
                message_scene=scene,
                peer_id=peer_id,
                sender_id=sender_id,
            ):
                return (
                    f"{cls.id(sender_id)} in {cls.id(peer_id)}"
                    if scene == "group"
                    else cls.id(sender_id)
                )
            # Fallback
            case _:
                return cls.id(data.sender_id)


@patcher
def patch_event(self: Event) -> str:
    return (
        f"[{H.event_type(self)}]: {H.apply(self)}"
        if type(self).get_event_description is Event.get_event_description
        else f"[{H.event_type(self)}]: {self.get_event_description()}"
    )


@patcher
def patch_message_event(self: MessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} from {H.source(self.data)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_friend_message_event(self: FriendMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} from {H.source(self.data)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_message_recall_event(self: MessageRecallEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.data.message_seq)} "
        f"from {H.source(self.data)} "
        f"deleted by {H.id(self.data.operator_id)}"
        f"{
            f' suffix={H.style.le(self.data.display_suffix)}'
            if self.data.display_suffix
            else ''
        }"
    )


@patcher
def patch_friend_nudge_event(self: FriendNudgeEvent) -> str:
    send = self.self_id if self.data.is_self_send else self.data.user_id
    recv = self.self_id if self.data.is_self_receive else self.data.user_id
    action = (
        f"[{self.data.display_action}:{self.data.display_action_img_url}]"
        if self.data.display_action_img_url
        else self.data.display_action
    )
    suffix = self.data.display_suffix
    return f"[{H.event_type(self)}]: {H.id(send)} {action} {H.id(recv)} {suffix}"


@patcher
def patch_group_nudge_event(self: GroupNudgeEvent) -> str:
    action = (
        f"[{self.data.display_action}:{self.data.display_action_img_url}]"
        if self.data.display_action_img_url
        else self.data.display_action
    )
    suffix = self.data.display_suffix
    return (
        f"[{H.event_type(self)}]: "
        f"[Group:{H.id(self.data.group_id)}]: "
        f"{H.id(self.data.sender_id)} {action} "
        f"{H.id(self.data.receiver_id)} {suffix}"
    )


@patcher
def patch_group_message_reaction_event(self: GroupMessageReactionEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Reaction {H.style.y(self.data.face_id)} "
        f"{'added to' if self.data.is_add else 'removed from'} "
        f"{H.id(self.data.message_seq)} "
        f"by {H.group_member_id(self.data.group_id, self.data.user_id)}]"
    )


@patcher
def patch_group_mute_event(self: GroupMuteEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"{H.group_member_id(self.data.group_id, self.data.user_id)} "
        f"{'muted' if self.data.duration > 0 else 'unmuted'} "
        f"by {H.id(self.data.operator_id)}"
        f"{
            f' for {H.style.y(self.data.duration)} seconds'
            if self.data.duration > 0
            else ''
        }"
    )


@patcher
def patch_group_whole_mute_event(self: GroupWholeMuteEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Group:{H.id(self.data.group_id)} "
        f"{'muted' if self.data.is_mute else 'unmuted'} "
        f"by {H.id(self.data.operator_id)}"
    )
