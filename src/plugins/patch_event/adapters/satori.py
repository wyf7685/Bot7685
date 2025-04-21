from typing import override

from nonebot.adapters.satori import MessageSegment
from nonebot.adapters.satori.event import (
    Event,
    PrivateMessageCreatedEvent,
    PrivateMessageDeletedEvent,
    PublicMessageCreatedEvent,
    PublicMessageDeletedEvent,
    ReactionAddedEvent,
    ReactionRemovedEvent,
)
from nonebot.utils import escape_tag

from ..highlight import Highlight as BaseHighlight
from ..patcher import patcher


class Highlight(BaseHighlight[MessageSegment]):
    @classmethod
    @override
    def segment(cls, segment: MessageSegment) -> str:
        return (
            f"<m>{escape_tag(segment.__class__.__name__)}</m>"
            f"(<i><y>type</y></i>={cls.apply(segment.type)},"
            f" <i><y>data</y></i>={cls.apply(segment.data)},"
            f" <i><y>children</y></i>={cls.apply(segment.children)})"
        )


@patcher
def patch_event(self: Event) -> str:
    return f"[{self.get_event_name()}]: {Highlight.apply(self)}"


@patcher
def patch_private_message_created_event(self: PrivateMessageCreatedEvent) -> str:
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{escape_tag(self.msg_id)}</c> from "
        f"<y>{escape_tag(self.user.name or self.user.nick or '')}</y>"
        f"(<c>{escape_tag(self.channel.id)}</c>): "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_private_message_deleted_event(self: PrivateMessageDeletedEvent) -> str:
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{escape_tag(self.msg_id)}</c> from "
        f"<y>{escape_tag(self.user.name or self.user.nick or '')}</y>"
        f"(<c>{escape_tag(self.channel.id)}</c>) deleted"
    )


@patcher
def patch_public_message_created_event(self: PublicMessageCreatedEvent) -> str:
    nick = (self.member.nick if self.member else None) or (
        self.user.name or self.user.nick or ""
    )
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{self.msg_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.user.id}</c>)"
        f"@[Group:<y>{self.channel.name or ''}</y>(<c>{self.channel.id}</c>)]: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_public_message_deleted_event(self: PublicMessageDeletedEvent) -> str:
    nick = (self.member.nick if self.member else None) or (
        self.user.name or self.user.nick or ""
    )
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{self.msg_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.user.id}</c>)"
        f"@[Group:<y>{self.channel.name or ''}</y>(<c>{self.channel.id}</c>)] "
        "deleted"
    )


@patcher
def patch_reaction_added_event(self: ReactionAddedEvent) -> str:
    return (
        f"[{self.get_event_name()}] "
        f"Reaction added to <c>{escape_tag(self.msg_id)}</c> "
        f"by <c>{self.user.id}</c>@[Group:<c>{self.guild.id}</c>]"
    )


@patcher
def patch_reaction_removed_event(self: ReactionRemovedEvent) -> str:
    return (
        f"[{self.get_event_name()}] "
        f"Reaction removed from <c>{escape_tag(self.msg_id)}</c> "
        f"by <c>{self.user.id}</c>@[Group:<c>{self.guild.id}</c>]"
    )
