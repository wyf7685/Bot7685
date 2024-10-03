import contextlib
from typing import TYPE_CHECKING, override

from nonebot.compat import model_dump
from nonebot.utils import escape_tag

from ..patcher import Patcher
from ..utils import color_repr, highlight_dict, highlight_list

if TYPE_CHECKING:
    from nonebot.adapters.satori import Message


def highlight_message(message: "Message") -> str:
    return (
        "["
        + ", ".join(
            f"<g>{escape_tag(seg.__class__.__name__)}</g>"
            f"(type={color_repr(seg.type, 'y')}, "
            f"data={highlight_dict(seg.data)}, "
            f"children={highlight_list(seg.children)})"
            for seg in message
        )
        + "]"
    )


with contextlib.suppress(ImportError):
    from nonebot.adapters.satori.event import (
        Event,
        PrivateMessageCreatedEvent,
        PrivateMessageDeletedEvent,
        PublicMessageCreatedEvent,
        PublicMessageDeletedEvent,
        ReactionAddedEvent,
        ReactionRemovedEvent,
    )

    @Patcher
    class PatchEvent(Event):
        @override
        def get_log_string(self) -> str:
            return f"[{self.get_event_name()}]: {highlight_dict(model_dump(self))}"

    @Patcher
    class PatchPrivateMessageCreatedEvent(PrivateMessageCreatedEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{escape_tag(self.msg_id)}</c> from "
                f"<y>{escape_tag(self.user.name or self.user.nick or '')}</y>"
                f"(<c>{escape_tag(self.channel.id)}</c>): "
                f"{highlight_message(self.get_message())}"
            )

    @Patcher
    class PatchPrivateMessageDeletedEvent(PrivateMessageDeletedEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{escape_tag(self.msg_id)}</c> from "
                f"<y>{escape_tag(self.user.name or self.user.nick or '')}</y>"
                f"(<c>{escape_tag(self.channel.id)}</c>) deleted"
            )

    @Patcher
    class PatchPublicMessageCreatedEvent(PublicMessageCreatedEvent):
        @override
        def get_log_string(self) -> str:
            nick = (self.member.nick if self.member else None) or (
                self.user.name or self.user.nick or ""
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.msg_id}</c> from "
                f"<y>{escape_tag(nick)}</y>(<c>{self.user.id}</c>)"
                f"@[Group:<y>{self.channel.name or ''}</y>(<c>{self.channel.id}</c>)]: "
                f"{highlight_message(self.get_message())}"
            )

    @Patcher
    class PatchPublicMessageDeletedEvent(PublicMessageDeletedEvent):
        @override
        def get_log_string(self) -> str:
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

    @Patcher
    class PatchReactionAddedEvent(ReactionAddedEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}] "
                f"Reaction added to <c>{escape_tag(self.msg_id)}</c> "
                f"by <c>{self.user.id}</c>@[Group:<c>{self.guild.id}</c>]"
            )

    @Patcher
    class PatchReactionRemovedEvent(ReactionRemovedEvent):
        @override
        def get_log_string(self) -> str:
            return (
                f"[{self.get_event_name()}] "
                f"Reaction removed from <c>{escape_tag(self.msg_id)}</c> "
                f"by <c>{self.user.id}</c>@[Group:<c>{self.guild.id}</c>]"
            )
