from nonebot.adapters.telegram.event import (
    ForumTopicEditedMessageEvent,
    ForumTopicMessageEvent,
    GroupEditedMessageEvent,
    GroupMessageEvent,
    PrivateEditedMessageEvent,
    PrivateMessageEvent,
)
from nonebot.utils import escape_tag

from ..highlight import Highlight
from ..patcher import patcher


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    chat = f"<c>{self.chat.id}</c>"
    if self.chat.title:
        chat = f"<y>{escape_tag(self.chat.title)}</y>({chat})"
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>)@[Chat {chat}]: "
        f"{Highlight.apply(self.original_message)}"
    )


@patcher
def patch_forum_topic_message_event(self: ForumTopicMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    chat = f"<c>{self.chat.id}</c>"
    if self.chat.title:
        chat = f"<y>{escape_tag(self.chat.title)}</y>({chat})"
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>)@[Chat {chat} "
        f"Thread <c>{self.message_thread_id}</c>]: "
        f"{Highlight.apply(self.original_message)}"
    )


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>): "
        f"{Highlight.apply(self.original_message)}"
    )


@patcher
def patch_group_edited_message_event(self: GroupEditedMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    chat = f"<c>{self.chat.id}</c>"
    if self.chat.title:
        chat = f"<y>{escape_tag(self.chat.title)}</y>({chat})"
    return (
        f"[{self.get_event_name()}]: "
        f"EditedMessage <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>)@[Chat {chat}]: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_forum_topic_edited_message_event(self: ForumTopicEditedMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    chat = f"<c>{self.chat.id}</c>"
    if self.chat.title:
        chat = f"<y>{escape_tag(self.chat.title)}</y>({chat})"
    return (
        f"[{self.get_event_name()}]: "
        f"EditedMessage <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>)@[Chat {chat} "
        f"Thread <c>{self.message_thread_id}</c>]: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_private_edited_message_event(self: PrivateEditedMessageEvent) -> str:
    nick = self.from_.first_name + (
        f" {self.from_.last_name}" if self.from_.last_name else ""
    )
    return (
        f"[{self.get_event_name()}]: "
        f"EditedMessage <c>{self.message_id}</c> from "
        f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>): "
        f"{Highlight.apply(self.get_message())}"
    )
