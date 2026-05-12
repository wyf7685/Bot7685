"""群分析领域数据模型。"""

from dataclasses import dataclass, field
from typing import Any

from src.service.llm import TokenUsage

from .value_objects import UnifiedMember


@dataclass
class SummaryTopic:
    """话题总结"""

    topic: str
    contributors: list[str]
    detail: str
    contributor_ids: list[str] = field(default_factory=list)


@dataclass
class UserTitle:
    """用户称号"""

    name: str
    user_id: str
    title: str
    mbti: str
    reason: str


@dataclass
class GoldenQuote:
    """群聊金句"""

    content: str
    sender: str
    reason: str
    user_id: str = ""


@dataclass
class QualityDimension:
    """聊天质量维度"""

    name: str
    percentage: float
    comment: str

    def with_color(self, color: str) -> QualityDimensionWithColor:
        return QualityDimensionWithColor(
            name=self.name,
            percentage=self.percentage,
            comment=self.comment,
            color=color,
        )


@dataclass
class QualityDimensionWithColor(QualityDimension):
    color: str


@dataclass
class QualityReview:
    """聊天质量锐评"""

    title: str
    subtitle: str
    dimensions: list[QualityDimension]
    summary: str


@dataclass
class UserActivity:
    """用户活跃数据"""

    user: UnifiedMember
    message_count: int = 0
    char_count: int = 0
    emoji_count: int = 0
    reply_count: int = 0
    hours: dict[int, int] = field(default_factory=lambda: dict.fromkeys(range(24), 0))
    last_message_time: int = 0

    @property
    def user_id(self) -> str:
        return self.user.user_id

    @property
    def nickname(self) -> str:
        return self.user.nickname

    def __add__(self, other: UserActivity) -> UserActivity:
        if self.user_id != other.user_id:
            raise ValueError("只能合并同一用户的活跃数据")
        return UserActivity(
            user=self.user,
            message_count=self.message_count + other.message_count,
            char_count=self.char_count + other.char_count,
            emoji_count=self.emoji_count + other.emoji_count,
            reply_count=self.reply_count + other.reply_count,
            hours={
                h: self.hours.get(h, 0) + other.hours.get(h, 0)
                for h in set(self.hours) | set(other.hours)
            },
            last_message_time=max(self.last_message_time, other.last_message_time),
        )


@dataclass
class UserActivityRanking:
    """用户活跃排名"""

    user_id: str
    nickname: str
    message_count: int
    char_count: int

    @classmethod
    def from_activity(cls, activity: UserActivity) -> UserActivityRanking:
        return cls(
            user_id=activity.user_id,
            nickname=activity.nickname,
            message_count=activity.message_count,
            char_count=activity.char_count,
        )


@dataclass
class EmojiStatistics:
    """表情统计"""

    face_count: int = 0
    mface_count: int = 0
    bface_count: int = 0
    sface_count: int = 0
    other_emoji_count: int = 0
    face_details: dict[str, int] = field(default_factory=dict)

    @property
    def total_emoji_count(self) -> int:
        return (
            self.face_count
            + self.mface_count
            + self.bface_count
            + self.sface_count
            + self.other_emoji_count
        )

    def __add__(self, other: EmojiStatistics) -> EmojiStatistics:
        return EmojiStatistics(
            face_count=self.face_count + other.face_count,
            mface_count=self.mface_count + other.mface_count,
            bface_count=self.bface_count + other.bface_count,
            sface_count=self.sface_count + other.sface_count,
            other_emoji_count=self.other_emoji_count + other.other_emoji_count,
            face_details={
                key: self.face_details.get(key, 0) + other.face_details.get(key, 0)
                for key in set(self.face_details) | set(other.face_details)
            },
        )


@dataclass
class ActivityVisualization:
    """活跃度可视化数据"""

    hourly_activity: dict[int, int] = field(default_factory=dict)
    daily_activity: dict[str, int] = field(default_factory=dict)
    user_activity_ranking: list[UserActivityRanking] = field(default_factory=list)
    peak_hours: list[int] = field(default_factory=list)
    activity_heatmap_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class GroupStatistics:
    """群聊统计"""

    message_count: int
    total_characters: int
    participant_count: int
    most_active_period: str
    golden_quotes: list[GoldenQuote]
    emoji_count: int
    emoji_statistics: EmojiStatistics = field(default_factory=EmojiStatistics)
    activity: ActivityVisualization = field(default_factory=ActivityVisualization)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    chat_quality_review: QualityReview | None = None
