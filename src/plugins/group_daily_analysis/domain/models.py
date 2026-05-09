"""群分析领域数据模型。"""

from dataclasses import dataclass, field
from typing import Any

from src.service.llm import TokenUsage


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


@dataclass
class ActivityVisualization:
    """活跃度可视化数据"""

    hourly_activity: dict[int, int] = field(default_factory=dict)
    daily_activity: dict[str, int] = field(default_factory=dict)
    user_activity_ranking: list[dict[str, Any]] = field(default_factory=list)
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
    activity_visualization: ActivityVisualization = field(
        default_factory=ActivityVisualization
    )
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    chat_quality_review: QualityReview | None = None
