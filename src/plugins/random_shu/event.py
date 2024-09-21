from typing import Literal, override

from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter
from nonebot.adapters.onebot.v11.event import NoticeEvent
from pydantic import BaseModel


class Like(BaseModel):
    emoji_id: str
    count: int


class GroupMsgEmojiLikeEvent(NoticeEvent):
    notice_type: Literal["group_msg_emoji_like"]  # pyright: ignore[reportIncompatibleVariableOverride]
    user_id: int
    group_id: int
    message_id: int
    likes: list[Like]

    @override
    def get_user_id(self) -> str:
        return str(self.user_id)

    @override
    def get_session_id(self) -> str:
        return f"group_{self.group_id}_{self.user_id}"


OneBotV11Adapter.add_custom_model(GroupMsgEmojiLikeEvent)
