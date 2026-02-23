from typing import override

from nonebot.adapters.satori import MessageSegment
from nonebot.adapters.satori.event import (
    PrivateMessageCreatedEvent,
    PrivateMessageDeletedEvent,
    PublicMessageCreatedEvent,
    PublicMessageDeletedEvent,
    ReactionAddedEvent,
    ReactionRemovedEvent,
)
from nonebot.adapters.satori.models import Channel, Guild, Member, User

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight[MessageSegment]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        return (
            f"{cls.style.lg(segment.__class__.__name__, escape=True)}"
            f"({cls.style.i_y('type')}={cls.apply(segment.type)},"
            f" {cls.style.i_y('data')}={cls.apply(segment.data)},"
            f" {cls.style.i_y('children')}={cls.apply(segment.children)})"
        )

    @classmethod
    def user(cls, user: User, member: Member | None = None) -> str:
        return cls.name(user.id, (member and member.nick) or user.name or user.nick)

    @classmethod
    def scene(cls, scene: Channel | Guild) -> str:
        return cls.name(scene.id, scene.name)


@patcher
def patch_private_message_created_event(self: PrivateMessageCreatedEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.msg_id)} "
        f"from {H.user(self.user)}: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_private_message_deleted_event(self: PrivateMessageDeletedEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.msg_id)} "
        f"from {H.user(self.user)} "
        f"deleted"
    )


@patcher
def patch_public_message_created_event(self: PublicMessageCreatedEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.msg_id)} "
        f"from {H.user(self.user, self.member)}"
        f"@[Group:{H.scene(self.channel)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_public_message_deleted_event(self: PublicMessageDeletedEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.msg_id)} "
        f"from {H.user(self.user, self.member)}"
        f"@[Group:{H.scene(self.channel)}] "
        "deleted"
    )


@patcher
def patch_reaction_added_event(self: ReactionAddedEvent) -> str:
    return (
        f"[{self}] "
        f"Reaction added to {H.id(self.msg_id)} "
        f"by {H.user(self.user)}"
        f"@[Group:{H.scene(self.guild)}]"
    )


@patcher
def patch_reaction_removed_event(self: ReactionRemovedEvent) -> str:
    return (
        f"[{self}] "
        f"Reaction removed from {H.id(self.msg_id)} "
        f"by {H.user(self.user)}"
        f"@[Group:{H.scene(self.guild)}]"
    )
