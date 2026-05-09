"""增量分析领域实体 — 滑动窗口批次存储架构。

核心概念：
- IncrementalBatch: 单次增量分析产生的独立批次数据，按批次独立存储
- IncrementalState: 报告生成时由多个批次合并而成的聚合视图（不持久化）

滑动窗口设计：
- 每次增量分析产生一个 IncrementalBatch，独立存储到 KV
- 最终报告时按 analysis_days × 24h 的时间窗口查询批次并合并
- 支持同一天多次发送报告，每次都基于当前时间窗口内的所有批次
"""

import time as time_mod
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from src.service.llm import TokenUsage

from .models import (
    EmojiStatistics,
    GoldenQuote,
    GroupStatistics,
    QualityReview,
    SummaryTopic,
    UserTitle,
)

_UTC8 = timezone(timedelta(hours=8))


@dataclass
class IncrementalIndex:
    """增量分析批次索引项，用于批次列表存储。

    每当产生一个新的 IncrementalBatch 时，都会在对应群组的
    索引列表中添加一个 IncrementalIndex，以便后续按时间窗口
    查询批次时快速定位相关批次 ID 和时间戳。
    """

    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time_mod.time)


@dataclass
class UserActivity:
    """用户活跃数据"""

    user_id: str
    nickname: str
    message_count: int = 0
    char_count: int = 0
    emoji_count: int = 0
    reply_count: int = 0
    hours: dict[int, int] = field(default_factory=lambda: dict.fromkeys(range(24), 0))
    last_message_time: int = 0

    def __add__(self, other: UserActivity) -> UserActivity:
        if self.user_id != other.user_id:
            raise ValueError("只能合并同一用户的活跃数据")
        return UserActivity(
            user_id=self.user_id,
            nickname=other.nickname,
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
class IncrementalBatch:
    """单次增量分析批次数据。

    每次增量分析执行完毕后产生一个 IncrementalBatch，
    包含该批次的所有统计数据和 LLM 分析结果，独立存储到 KV。
    """

    group_id: str = ""
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time_mod.time)

    # 统计数据
    messages_count: int = 0
    characters_count: int = 0
    hourly_msg_counts: dict[int, int] = field(
        default_factory=lambda: dict.fromkeys(range(24), 0)
    )
    hourly_char_counts: dict[int, int] = field(
        default_factory=lambda: dict.fromkeys(range(24), 0)
    )

    # 用户活跃数据
    user_stats: dict[str, UserActivity] = field(default_factory=dict)

    # 表情统计
    emoji_stats: EmojiStatistics = field(default_factory=EmojiStatistics)

    # LLM 分析结果
    topics: list[SummaryTopic] = field(default_factory=list)
    golden_quotes: list[GoldenQuote] = field(default_factory=list)

    # Token 消耗
    token_usage: TokenUsage = field(default_factory=TokenUsage)

    # 增量追踪
    chat_quality_review: QualityReview | None = None
    last_message_timestamp: int = 0
    participant_ids: list[str] = field(default_factory=list)

    # def get_summary(self) -> dict[str, Any]:
    #     return {
    #         "batch_id": self.batch_id[:8],
    #         "timestamp": datetime.fromtimestamp(self.timestamp, tz=_UTC8).strftime(
    #             "%Y-%m-%d %H:%M:%S"
    #         ),
    #         "messages_count": self.messages_count,
    #         "topics_count": len(self.topics),
    #         "quotes_count": len(self.golden_quotes),
    #         "participants": len(self.participant_ids),
    #     }


@dataclass
class IncrementalState:
    """增量分析聚合视图（报告时使用）。

    由多个 IncrementalBatch 合并而成，不直接持久化。
    IncrementalMergeService.merge_batches() 负责从批次列表构建此对象。
    """

    group_id: str = ""
    window_start: float = 0.0
    window_end: float = 0.0

    # 合并后的 LLM 分析结果
    topics: list[SummaryTopic] = field(default_factory=list)
    golden_quotes: list[GoldenQuote] = field(default_factory=list)
    chat_quality_review: QualityReview | None = None
    all_quality_reviews: list[QualityReview] = field(default_factory=list)

    # 合并后的统计数据（按小时）
    hourly_message_counts: dict[int, int] = field(default_factory=dict)
    hourly_character_counts: dict[int, int] = field(default_factory=dict)

    # 用户活跃数据
    user_activities: dict[str, UserActivity] = field(default_factory=dict)

    # 表情统计
    emoji_counts: EmojiStatistics = field(default_factory=EmojiStatistics)

    # 汇总统计
    total_message_count: int = 0
    total_character_count: int = 0
    total_analysis_count: int = 0
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)

    # 增量跟踪
    last_analyzed_message_timestamp: int = 0
    all_participant_ids: set[str] = field(default_factory=set)

    # 元数据
    created_at: float = field(default_factory=time_mod.time)
    updated_at: float = field(default_factory=time_mod.time)

    def get_peak_hours(self, top_n: int = 3) -> list[int]:
        if not self.hourly_message_counts:
            return []
        sorted_hours = sorted(
            self.hourly_message_counts.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        return [int(h) for h, _ in sorted_hours[:top_n]]

    def get_most_active_period(self) -> str:
        peak = self.get_peak_hours(1)
        if not peak:
            return "未知"
        hour = peak[0]
        return f"{hour:02d}:00-{hour + 1:02d}:00"

    def get_user_activity_ranking(self, top_n: int = 10) -> list[UserActivityRanking]:
        users = sorted(
            map(UserActivityRanking.from_activity, self.user_activities.values()),
            key=lambda x: x.message_count,
            reverse=True,
        )
        return users[:top_n]

    def get_window_date_str(self) -> str:
        if self.window_start <= 0 or self.window_end <= 0:
            return datetime.now().strftime("%Y-%m-%d")
        start_date = datetime.fromtimestamp(self.window_start, tz=_UTC8).strftime(
            "%Y-%m-%d"
        )
        end_date = datetime.fromtimestamp(self.window_end, tz=_UTC8).strftime(
            "%Y-%m-%d"
        )
        if start_date == end_date:
            return end_date
        return f"{start_date} ~ {end_date}"

    def is_duplicate_topic(
        self,
        new_topic: SummaryTopic,
        threshold: float = 0.6,
    ) -> bool:
        new_name = new_topic.topic
        if not new_name:
            return False
        for existing in self.topics:
            existing_name = existing.topic
            if not existing_name:
                continue
            similarity = IncrementalState.char_overlap_similarity(
                new_name, existing_name
            )
            if similarity >= threshold:
                return True
        return False

    def is_duplicate_quote(
        self,
        new_quote: GoldenQuote,
        threshold: float = 0.7,
    ) -> bool:
        new_content = new_quote.content
        if not new_content:
            return False
        for existing in self.golden_quotes:
            existing_content = existing.content
            if not existing_content:
                continue
            similarity = IncrementalState.char_overlap_similarity(
                new_content, existing_content
            )
            if similarity >= threshold:
                return True
        return False

    @staticmethod
    def char_overlap_similarity(s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        set1 = set(s1)
        set2 = set(s2)
        intersection = set1 & set2
        union = set1 | set2
        if not union:
            return 0.0
        return len(intersection) / len(union)

    # def get_summary(self) -> dict[str, Any]:
    #     return {
    #         "group_id": self.group_id,
    #         "window": self.get_window_date_str(),
    #         "total_messages": self.total_message_count,
    #         "total_characters": self.total_character_count,
    #         "total_analyses": self.total_analysis_count,
    #         "topics_count": len(self.topics),
    #         "quotes_count": len(self.golden_quotes),
    #         "participants": len(self.all_participant_ids),
    #         "total_tokens": self.total_token_usage.total_tokens,
    #         "last_analysis_time": (
    #             datetime.fromtimestamp(self.updated_at, tz=_UTC8).strftime("%H:%M:%S")
    #             if self.updated_at
    #             else "无"
    #         ),
    #         "peak_hours": self.get_peak_hours(3),
    #     }


@dataclass
class IncrementalAnalysisResult:
    """增量分析结果数据结构"""

    statistics: GroupStatistics
    topics: list[SummaryTopic]
    golden_quotes: list[GoldenQuote]
    user_titles: list[UserTitle]
    user_analysis: dict[str, UserActivity]
    chat_quality_review: QualityReview | None
