import contextlib
from typing import override

from nonebot.utils import escape_tag

from ..highlight import Highlight
from ..patcher import Patcher

with contextlib.suppress(ImportError):
    from nonebot.adapters.telegram.event import (
        GroupEditedMessageEvent,
        GroupMessageEvent,
        PrivateEditedMessageEvent,
        PrivateMessageEvent,
    )

    @Patcher
    class PatchGroupMessageEvent(GroupMessageEvent):
        @override
        def get_log_string(self) -> str:
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
                f"{Highlight.apply(self.get_message())}"
            )

    @Patcher
    class PatchPrivateMessageEvent(PrivateMessageEvent):
        @override
        def get_log_string(self) -> str:
            nick = self.from_.first_name + (
                f" {self.from_.last_name}" if self.from_.last_name else ""
            )
            return (
                f"[{self.get_event_name()}]: "
                f"Message <c>{self.message_id}</c> from "
                f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>): "
                f"{Highlight.apply(self.get_message())}"
            )

    @Patcher
    class PatchGroupEditedMessageEvent(GroupEditedMessageEvent):
        @override
        def get_log_string(self) -> str:
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

    @Patcher
    class PatchPrivateEditedMessageEvent(PrivateEditedMessageEvent):
        @override
        def get_log_string(self) -> str:
            nick = self.from_.first_name + (
                f" {self.from_.last_name}" if self.from_.last_name else ""
            )
            return (
                f"[{self.get_event_name()}]: "
                f"EditedMessage <c>{self.message_id}</c> from "
                f"<y>{escape_tag(nick)}</y>(<c>{self.from_.id}</c>): "
                f"{Highlight.apply(self.get_message())}"
            )