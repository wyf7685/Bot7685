from nonebot.adapters.telegram.event import (
    ForumTopicEditedMessageEvent,
    ForumTopicMessageEvent,
    GroupEditedMessageEvent,
    GroupMessageEvent,
    PrivateEditedMessageEvent,
    PrivateMessageEvent,
)
from nonebot.adapters.telegram.model import Chat, User

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight):
    @classmethod
    def chat(cls, chat: Chat) -> str:
        return cls.name(chat.id, chat.title)

    @classmethod
    def user(cls, user: User) -> str:
        name = user.first_name + (f" {user.last_name}" if user.last_name else "")
        return cls.name(user.id, name)


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.from_)}"
        f"@[Chat {H.chat(self.chat)}]: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_forum_topic_message_event(self: ForumTopicMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.from_)}"
        f"@[Chat {H.chat(self.chat)}]: "
        f"Thread {H.id(self.message_thread_id)}]: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.user(self.from_)}: "
        f"{H.apply(self.original_message)}"
    )


@patcher
def patch_group_edited_message_event(self: GroupEditedMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"EditedMessage {H.id(self.message_id)} "
        f"from {H.user(self.from_)}"
        f"@[Chat {H.chat(self.chat)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_forum_topic_edited_message_event(self: ForumTopicEditedMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"EditedMessage {H.id(self.message_id)} "
        f"from {H.user(self.from_)}"
        f"@[Chat {H.chat(self.chat)} "
        f"Thread {H.id(self.message_thread_id)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_private_edited_message_event(self: PrivateEditedMessageEvent) -> str:
    return (
        f"[{H.event_type(self)}]: "
        f"EditedMessage {H.id(self.message_id)} "
        f"from {H.user(self.from_)}: "
        f"{H.apply(self.get_message())}"
    )
