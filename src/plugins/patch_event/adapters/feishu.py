import datetime as dt
import functools
from typing import LiteralString, override

import nonebot
from nonebot.adapters.feishu import Adapter, NoticeEvent
from nonebot.adapters.feishu.event import Event, GroupMessageEvent, PrivateMessageEvent
from nonebot.adapters.feishu.models import UserId
from pydantic import BaseModel

from ..highlight import Highlight
from ..patcher import patcher


class H(Highlight): ...


@patcher
def patch_event(self: Event) -> str:
    return f"[{H.event_type(self.get_event_name())}]: {H.apply(self)}"


@patcher
def patch_private_message_event(self: PrivateMessageEvent) -> str:
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"Message {H.id(self.message_id)} from "
        f"{H.id(self.get_user_id())}"
        f"@[{H.style.y(self.event.message.chat_type)}:"
        f"{H.id(self.event.message.chat_id)}]: "
        f"{H.apply(self.get_message())}"
    )


@patcher
def patch_group_message_event(self: GroupMessageEvent) -> str:
    return (
        f"[{H.event_type(self.get_event_name())}]: "
        f"Message {H.id(self.message_id)} "
        f"from {H.id(self.get_user_id())}"
        f"@[{H.style.y(self.event.message.chat_type)}:"
        f"{H.id(self.event.message.chat_id)}]: "
        f"{H.apply(self.get_message())}"
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

    @functools.cached_property
    def last_message_create_time(self) -> dt.datetime:
        timestamp = float(self.event.last_message_create_time) / 1000
        return dt.datetime.fromtimestamp(timestamp)  # noqa: DTZ006

    @override
    def get_log_string(self) -> str:
        return (
            f"[{H.event_type(self.get_event_name())}]: "
            f"{H.id(self.get_user_id())}"
            f"@[{H.style.y('p2p')}:{H.id(self.event.chat_id)}] entered chat, "
            f"last message: {H.id(self.event.last_message_id)} "
            f"at {H.time(self.last_message_create_time)}"
        )


@nonebot.get_driver().on_startup
async def register_models() -> None:
    Adapter.add_custom_model(P2PChatEnteredEvent)
