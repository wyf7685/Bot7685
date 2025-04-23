from nonebot.adapters.feishu.event import Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.utils import escape_tag

from src.plugins.patch_event.highlight import Highlight
from src.plugins.patch_event.patcher import patcher


@patcher
def patch_event(self: Event) -> str:
    return f"[{self.get_event_name()}]: {Highlight.apply(self)}"


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{escape_tag(self.message_id)}</c> from "
        f"<c>{self.get_user_id()}</c>"
        f"@[<y>{self.event.message.chat_type}</y>:"
        f"<c>{self.event.message.chat_id}</c>]: "
        f"{Highlight.apply(self.get_message())}"
    )


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    return (
        f"[{self.get_event_name()}]: "
        f"Message <c>{escape_tag(self.message_id)}</c> from "
        f"<c>{self.get_user_id()}</c>"
        f"@[<y>{self.event.message.chat_type}</y>:"
        f"<c>{self.event.message.chat_id}</c>]: "
        f"{Highlight.apply(self.get_message())}"
    )
