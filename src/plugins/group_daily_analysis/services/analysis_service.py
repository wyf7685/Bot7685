"""分析编排服务 — 协调消息获取、统计、LLM 分析。"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from nonebot.log import logger
from nonebot_plugin_uninfo import Session

from ..analyzers.chat_quality import ChatQualityAnalyzer
from ..analyzers.golden_quote import GoldenQuoteAnalyzer
from ..analyzers.topic import TopicAnalyzer
from ..analyzers.user_title import UserTitleAnalyzer
from ..config import config
from ..domain.models import (
    GoldenQuote,
    GroupStatistics,
    QualityReview,
    SummaryTopic,
    TokenUsage,
    UserTitle,
)
from ..domain.value_objects import UnifiedMessage
from ..services.message_service import fetch_group_messages


@dataclass
class AnalysisResult:
    """分析结果聚合"""

    group_id: str
    group_name: str
    messages: list[UnifiedMessage]
    statistics: GroupStatistics
    topics: list[SummaryTopic] = field(default_factory=list)
    user_titles: list[UserTitle] = field(default_factory=list)
    golden_quotes: list[GoldenQuote] = field(default_factory=list)
    chat_quality: QualityReview | None = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)


async def run_daily_analysis(
    session: Session,
    days: int | None = None,
    system_prompt: str | None = None,
) -> AnalysisResult | None:
    """执行一次完整的群聊日常分析。

    Args:
        session: uninfo 注入的 Session
        days: 分析天数，为 None 时使用配置默认值
        system_prompt: 可选的系统提示词

    Returns:
        AnalysisResult 或 None（消息不足时）
    """
    days = days or config.analysis_days

    # 1. 拉取消息
    messages = await fetch_group_messages(session, days=days)
    if len(messages) < config.min_messages:
        logger.warning(
            f"群 {session.scene.id} 消息不足: {len(messages)} < {config.min_messages}"
        )
        return None

    # 2. 基础统计
    statistics = _calculate_statistics(messages)

    # 3. LLM 分析（并发）
    topics: list[SummaryTopic] = []
    user_titles: list[UserTitle] = []
    golden_quotes: list[GoldenQuote] = []
    chat_quality: QualityReview | None = None
    token_usage = TokenUsage()

    features = config.features

    # 话题分析
    if features.topic_enabled:
        analyzer = TopicAnalyzer(max_topics=features.max_topics)
        result, usage = await analyzer.analyze(messages, system_prompt)
        topics = result
        token_usage += usage

    # 用户称号分析
    if features.user_title_enabled:
        analyzer = UserTitleAnalyzer(max_titles=features.max_user_titles)
        result, usage = await analyzer.analyze(messages, system_prompt)
        user_titles = result
        token_usage += usage

    # 金句分析
    if features.golden_quote_enabled:
        analyzer = GoldenQuoteAnalyzer(max_quotes=features.max_golden_quotes)
        result, usage = await analyzer.analyze(messages, system_prompt)
        golden_quotes = result
        token_usage += usage

    # 聊天质量分析
    if features.chat_quality_enabled:
        analyzer = ChatQualityAnalyzer()
        result, usage = await analyzer.analyze(messages, system_prompt)
        if result:
            chat_quality = result[0]
        token_usage += usage

    statistics.golden_quotes = golden_quotes
    statistics.token_usage = token_usage
    statistics.chat_quality_review = chat_quality

    return AnalysisResult(
        group_id=session.scene.id,
        group_name=session.scene.name or session.scene.id,
        messages=messages,
        statistics=statistics,
        topics=topics,
        user_titles=user_titles,
        golden_quotes=golden_quotes,
        chat_quality=chat_quality,
        token_usage=token_usage,
    )


def _calculate_statistics(messages: list[UnifiedMessage]) -> GroupStatistics:
    """计算基础统计数据。"""

    participant_ids: set[str] = set()
    total_chars = 0
    emoji_count = 0
    hour_counter: Counter[int] = Counter()

    for msg in messages:
        participant_ids.add(msg.sender_id)
        total_chars += msg.get_text_length()
        emoji_count += msg.get_emoji_count()
        hour_counter[msg.get_datetime().hour] += 1

    peak_hour = hour_counter.most_common(1)[0][0] if hour_counter else 0
    most_active_period = f"{peak_hour}:00-{peak_hour + 1}:00"

    return GroupStatistics(
        message_count=len(messages),
        total_characters=total_chars,
        participant_count=len(participant_ids),
        most_active_period=most_active_period,
        golden_quotes=[],
        emoji_count=emoji_count,
    )
