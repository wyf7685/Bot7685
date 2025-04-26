from typing import LiteralString, override

import nonebot
from nonebot.adapters.feishu import Adapter, NoticeEvent
from nonebot.adapters.feishu.event import Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.feishu.models import UserId
from nonebot.utils import escape_tag
from pydantic import BaseModel

from ..highlight import Highlight
from ..patcher import patcher


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


class PrivateChatEnteredEventDetail(BaseModel):
    chat_id: str
    last_message_create_time: str
    last_message_id: str
    operator_id: UserId


class P2PChatEnteredEvent(NoticeEvent):
    __event__: LiteralString = "im.chat.access_event.bot_p2p_chat_entered_v1"
    event: PrivateChatEnteredEventDetail  # pyright: ignore[reportIncompatibleVariableOverride]

    @override
    def get_user_id(self) -> str:
        return self.event.operator_id.open_id

    def get_all_user_id(self) -> UserId:
        return self.event.operator_id

    @override
    def get_session_id(self) -> str:
        return f"p2p_{self.event.chat_id}_{self.get_user_id()}"

    @override
    def is_tome(self) -> bool:
        return True

    @override
    def get_log_string(self) -> str:
        return (
            f"[{self.get_event_name()}]: "
            f"<c>{self.get_user_id()}</c>"
            f"@[<y>p2p</y>:<c>{self.event.chat_id}</c>] entered chat, "
            f"last message: <c>{self.event.last_message_id}</c> "
            f"at <c>{self.event.last_message_create_time}</c>"
        )


@nonebot.get_driver().on_startup
async def register_models() -> None:
    Adapter.add_custom_model(P2PChatEnteredEvent)
