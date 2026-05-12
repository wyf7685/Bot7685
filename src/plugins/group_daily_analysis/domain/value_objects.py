"""统一消息值对象 — 适配 chatrecorder 记录。"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class MessageContentType(Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    EMOJI = "emoji"
    REPLY = "reply"
    FORWARD = "forward"
    AT = "at"
    VOICE = "voice"
    VIDEO = "video"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class MessageContent:
    """消息内容片段"""

    type: MessageContentType
    text: str = ""
    url: str = ""
    emoji_id: str = ""
    at_user_id: str = ""


@dataclass(frozen=True, slots=True)
class UnifiedMember:
    """群成员信息"""

    user_id: str
    nickname: str
    card: str | None = None
    avatar_url: str | None = None

    @property
    def display_name(self) -> str:
        return self.card or self.nickname or self.user_id

    def __hash__(self) -> int:
        return hash(self.user_id)


@dataclass(frozen=True, slots=True)
class UnifiedMessage:
    """统一消息格式

    chatrecorder 的 MessageRecord 经转换后填入此结构，
    供统计服务和 LLM 分析器消费。
    """

    message_id: str
    sender: UnifiedMember
    group_id: str
    text_content: str
    contents: tuple[MessageContent, ...] = field(default_factory=tuple)
    timestamp: int = 0
    platform: str = "unknown"
    reply_to_id: str | None = None
    sender_card: str | None = None

    @property
    def sender_id(self) -> str:
        return self.sender.user_id

    @property
    def display_name(self) -> str:
        return self.sender.display_name

    @property
    def has_text(self) -> bool:
        return bool(self.text_content.strip())

    def get_emoji_count(self) -> int:
        return sum(1 for c in self.contents if c.type == MessageContentType.EMOJI)

    def get_text_length(self) -> int:
        return len(self.text_content)

    def get_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp, UTC)
