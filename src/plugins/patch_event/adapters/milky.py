from typing import Literal, Protocol, cast, override

from nonebot.adapters.milky.event import (
    Event,
    FriendMessageEvent,
    FriendNudgeEvent,
    GroupNudgeEvent,
    MessageEvent,
    MessageRecallEvent,
)
from nonebot.adapters.milky.message import MessageSegment
from nonebot.adapters.milky.model.base import ModelBase
from nonebot.adapters.milky.model.common import Friend, Group, Member
from nonebot.adapters.milky.model.message import IncomingMessage

from ..highlight import Highlight
from ..patcher import patcher


class ModelWithScene(Protocol):
    message_scene: Literal["friend", "group", "temp"]
    sender_id: int
    peer_id: int


class H(Highlight[MessageSegment]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        if segment.is_text():
            return segment.data["text"]

        shown_data = {k: v for k, v in segment.data.items() if not k.startswith("_")}
        return f"[{cls.style.le(segment.type)}: {cls.apply(shown_data)}]"

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
    def source(cls, data: ModelWithScene) -> str:
        match cast("ModelBase", data):
            case IncomingMessage(message_scene="friend", friend=friend):
                return cls.friend(friend) if friend else cls.id(data.sender_id)
            case IncomingMessage(
                message_scene="group",
                group=group,
                group_member=member,
            ):
                return (
                    cls.group_member(group, member)
                    if group and member
                    else f"{cls.id(data.sender_id)}@[Group:{cls.id(data.peer_id)}]"
                )
            case IncomingMessage(message_scene="temp", group=group):
                return (
                    f"{cls.id(data.sender_id)}@[Temp:{cls.group(group)}]"
                    if group
                    else cls.id(data.sender_id)
                )
            case ModelBase(message_scene=scene, peer_id=peer_id, sender_id=sender_id):
                return (
                    f"{cls.apply(sender_id)} in {cls.apply(peer_id)}"
                    if scene == "group"
                    else cls.apply(sender_id)
                )
            case _:
                return cls.id(data.sender_id)


@patcher
def patch_event(self: Event) -> str:
    return f"[{H.event_type(self.get_event_name())}]: {H.apply(self)}"


@patcher
def patch_message_event(self: MessageEvent) -> str:
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.source(self.data)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_friend_message_event(self: FriendMessageEvent) -> str:
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.source(self.data)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_message_recall_event(self: MessageRecallEvent) -> str:
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"Message seq={H.id(self.data.message_seq)} "
        f"from {H.source(self.data)} "
        f"deleted"
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
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"{H.id(send)} {action} {H.id(recv)} {suffix}"
    )


@patcher
def patch_group_nudge_event(self: GroupNudgeEvent) -> str:
    action = (
        f"[{self.data.display_action}:{self.data.display_action_img_url}]"
        if self.data.display_action_img_url
        else self.data.display_action
    )
    suffix = self.data.display_suffix
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"[Group:{H.id(self.data.group_id)}]: "
        f"{H.id(self.data.sender_id)} {action} "
        f"{H.id(self.data.receiver_id)} {suffix}"
    )
