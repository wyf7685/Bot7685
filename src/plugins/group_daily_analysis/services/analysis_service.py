"""分析编排服务 — 协调消息获取、统计、LLM 分析。"""

import asyncio
import time as time_mod
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from nonebot.adapters import Bot
from nonebot.log import logger
from nonebot_plugin_uninfo import Session

from src.service.llm import TokenUsage

from ..analyzers.chat_quality import ChatQualityAnalyzer
from ..analyzers.golden_quote import GoldenQuoteAnalyzer
from ..analyzers.topic import TopicAnalyzer
from ..analyzers.user_title import UserTitleAnalyzer, UserTitleInput
from ..config import config
from ..domain.incremental import IncrementalBatch, UserActivity
from ..domain.models import (
    ActivityVisualization,
    EmojiStatistics,
    GoldenQuote,
    GroupStatistics,
    QualityReview,
    SummaryTopic,
    UserTitle,
)
from ..domain.value_objects import UnifiedMember, UnifiedMessage
from ..persistence.incremental_store import IncrementalStore
from ..services.incremental_merge import IncrementalMergeService
from ..services.message_service import fetch_group_messages

_incremental_store = IncrementalStore()
_merge_service = IncrementalMergeService()


@dataclass
class AnalysisResult:
    """分析结果聚合"""

    group_id: str
    group_name: str
    messages: list[UnifiedMessage]
    members: set[UnifiedMember]
    statistics: GroupStatistics
    topics: list[SummaryTopic] = field(default_factory=list)
    user_titles: list[UserTitle] = field(default_factory=list)
    golden_quotes: list[GoldenQuote] = field(default_factory=list)
    chat_quality: QualityReview | None = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)


async def run_daily_analysis(
    bot: Bot,
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
    messages, members = await fetch_group_messages(bot, session, days=days)
    if len(messages) < config.min_messages:
        logger.warning(
            f"群 {session.scene.id} 消息不足: {len(messages)} < {config.min_messages}"
        )
        return None

    # 2. 基础统计
    statistics = _calculate_statistics(messages)

    # 2.5. 预计算用户活跃数据（供称号分析用，同步无 API 调用）
    features = config.features
    user_title_input: UserTitleInput | None = None
    if features.user_title_enabled:
        user_activities = _compute_user_stats(messages)
        user_title_input = UserTitleInput.from_user_activities(
            user_activities,
            max_users=features.max_user_titles,
        )

    # 3. LLM 分析（并行）
    async def run_topic() -> tuple[list[SummaryTopic], TokenUsage]:
        if not features.topic_enabled:
            return [], TokenUsage()
        return await TopicAnalyzer(max_topics=features.max_topics).analyze(
            messages, system_prompt
        )

    async def run_user_title() -> tuple[list[UserTitle], TokenUsage]:
        if not features.user_title_enabled or not user_title_input:
            return [], TokenUsage()
        return await UserTitleAnalyzer(max_titles=features.max_user_titles).analyze(
            user_title_input, system_prompt
        )

    async def run_golden_quote() -> tuple[list[GoldenQuote], TokenUsage]:
        if not features.golden_quote_enabled:
            return [], TokenUsage()
        return await GoldenQuoteAnalyzer(max_quotes=features.max_golden_quotes).analyze(
            messages, system_prompt
        )

    async def run_chat_quality() -> tuple[list[QualityReview], TokenUsage]:
        if not features.chat_quality_enabled:
            return [], TokenUsage()
        return await ChatQualityAnalyzer().analyze(messages, system_prompt)

    (
        (topics, _),
        (user_titles, _),
        (golden_quotes, _),
        (chat_quality, _),
    ) = results = await asyncio.gather(
        run_topic(),
        run_user_title(),
        run_golden_quote(),
        run_chat_quality(),
    )
    token_usage = sum((usage for _, usage in results), TokenUsage())

    statistics.golden_quotes = golden_quotes
    statistics.token_usage = token_usage
    statistics.chat_quality_review = chat_quality[0] if chat_quality else None

    return AnalysisResult(
        group_id=session.scene.id,
        group_name=session.scene.name or session.scene.id,
        messages=messages,
        members=members,
        statistics=statistics,
        topics=topics,
        user_titles=user_titles,
        golden_quotes=golden_quotes,
        chat_quality=chat_quality[0] if chat_quality else None,
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
        activity=ActivityVisualization(hourly_activity=dict(hour_counter)),
    )


# ══════════════════════════════════════════════════════════
#  增量分析
# ══════════════════════════════════════════════════════════


async def run_incremental_analysis(
    bot: Bot,
    session: Session,
    days: int | None = None,
) -> IncrementalBatch | None:
    """执行一次增量分析，将结果保存为独立批次。

    Args:
        session: uninfo 注入的 Session
        days: 分析天数

    Returns:
        IncrementalBatch 或 None（消息不足时）
    """
    incr_config = config.incremental
    group_id = session.scene.id
    days = days or config.analysis_days

    # 1. 获取水位线
    last_ts = await _incremental_store.get_last_analyzed_timestamp(group_id)

    # 2. 拉取新消息
    messages, members = await fetch_group_messages(
        bot, session, days=days, since_timestamp=last_ts
    )

    # 3. 二次去重
    if last_ts > 0:
        messages = [m for m in messages if int(m.timestamp) > int(last_ts)]

    # 4. 检查最小消息阈值
    if len(messages) < incr_config.min_messages:
        logger.info(
            f"群 {group_id} 增量分析: 新消息数 ({len(messages)}) "
            f"未达到阈值 ({incr_config.min_messages})"
        )
        return None

    # 5. 计算批次统计数据
    hourly_msg_counts, hourly_char_counts = _compute_hourly_counts(messages)
    user_stats = _compute_user_stats(messages)
    emoji_stats = _compute_emoji_stats(messages)
    characters_count = sum(msg.get_text_length() for msg in messages)
    participant_ids = list({msg.sender_id for msg in messages})
    last_message_timestamp = max((msg.timestamp for msg in messages), default=0)

    # 6. LLM 增量分析（仅话题 + 金句）
    features = config.features

    topic_analyzer = TopicAnalyzer(max_topics=features.max_topics)
    golden_quote_analyzer = GoldenQuoteAnalyzer(max_quotes=features.max_golden_quotes)

    topic_analyzer.incremental_max_count = incr_config.topics_per_batch
    golden_quote_analyzer.incremental_max_count = incr_config.quotes_per_batch

    async def placeholder() -> tuple[list[Any], TokenUsage]:
        return [], TokenUsage()

    (topics, topic_usage), (golden_quotes, quote_usage) = await asyncio.gather(
        topic_analyzer.analyze(messages) if features.topic_enabled else placeholder(),
        golden_quote_analyzer.analyze(messages)
        if features.golden_quote_enabled
        else placeholder(),
    )

    # 7. 构建批次
    batch = IncrementalBatch(
        group_id=group_id,
        timestamp=time_mod.time(),
        messages_count=len(messages),
        characters_count=characters_count,
        hourly_msg_counts=hourly_msg_counts,
        hourly_char_counts=hourly_char_counts,
        members=members,
        user_stats=user_stats,
        emoji_stats=emoji_stats,
        topics=topics,
        golden_quotes=golden_quotes,
        token_usage=topic_usage + quote_usage,
        last_message_timestamp=last_message_timestamp,
        participant_ids=participant_ids,
    )

    # 8. 保存批次并更新水位线
    await _incremental_store.save_batch(batch)
    safe_ts = min(last_message_timestamp, int(time_mod.time()) + 60)
    await _incremental_store.update_last_analyzed_timestamp(group_id, safe_ts)

    logger.info(
        f"群 {group_id} 增量分析完成: "
        f"本批次消息={len(messages)}, "
        f"新话题={len(topics)}, 新金句={len(golden_quotes)}"
    )

    return batch


async def run_incremental_final_report(
    session: Session,
    days: int | None = None,
) -> AnalysisResult | None:
    """基于滑动窗口内的增量批次生成最终报告。

    Args:
        session: uninfo 注入的 Session
        days: 分析天数

    Returns:
        AnalysisResult 或 None（无增量数据时）
    """
    group_id = session.scene.id
    days = days or config.analysis_days
    features = config.features

    # 1. 计算滑动窗口
    window_end = time_mod.time()
    window_start = window_end - (days * 24 * 3600)

    # 2. 查询窗口内的批次
    batches = await _incremental_store.query_batches(group_id, window_start, window_end)

    if not batches:
        logger.warning(f"群 {group_id} 滑动窗口内无增量分析数据")
        return None

    # 3. 合并批次
    state = _merge_service.merge_batches(batches, window_start, window_end)

    # 4. 用户称号分析（使用合并后的用户活跃数据）
    user_titles: list[UserTitle] = []
    if features.user_title_enabled and state.user_activities:
        user_title_input = UserTitleInput.from_user_activities(
            state.user_activities,
            max_users=features.max_user_titles,
        )
        if user_title_input:
            try:
                titles_result, title_token_usage = await UserTitleAnalyzer(
                    max_titles=features.max_user_titles
                ).analyze(user_title_input)
                user_titles = titles_result[: features.max_user_titles]
                state.total_token_usage += title_token_usage
            except Exception as e:
                logger.error(f"增量最终报告用户称号分析失败: {e}")

    # 5. 构建 analysis_result
    incr_result = _merge_service.build_analysis_result(state, user_titles)
    statistics = incr_result.statistics
    topics = incr_result.topics
    built_quotes = incr_result.golden_quotes

    logger.info(
        f"群 {group_id} 增量最终报告完成: "
        f"窗口={state.get_window_date_str()}, "
        f"累计消息={state.total_message_count}, "
        f"话题={len(topics)}, 金句={len(built_quotes)}, "
        f"批次={state.total_analysis_count}"
    )

    return AnalysisResult(
        group_id=group_id,
        group_name=session.scene.name or group_id,
        messages=[],
        members=set(),
        statistics=statistics,
        topics=topics,
        user_titles=user_titles,
        golden_quotes=built_quotes,
        chat_quality=statistics.chat_quality_review,
        token_usage=state.total_token_usage,
    )


# ══════════════════════════════════════════════════════════
#  增量分析辅助函数
# ══════════════════════════════════════════════════════════


def _compute_hourly_counts(
    messages: list[UnifiedMessage],
) -> tuple[dict[int, int], dict[int, int]]:
    hourly_msg: dict[int, int] = {}
    hourly_char: dict[int, int] = {}
    for msg in messages:
        hour = msg.get_datetime().hour
        hourly_msg[hour] = hourly_msg.get(hour, 0) + 1
        hourly_char[hour] = hourly_char.get(hour, 0) + msg.get_text_length()
    return hourly_msg, hourly_char


def _compute_user_stats(messages: list[UnifiedMessage]) -> dict[str, UserActivity]:
    user_data: dict[str, UserActivity] = {}
    for msg in messages:
        uid = msg.sender_id
        if uid in user_data:
            user_data[uid] += msg
        else:
            user_data[uid] = UserActivity.from_message(msg)
    return user_data


def _compute_emoji_stats(
    messages: list[UnifiedMessage],
) -> EmojiStatistics:
    face_count = 0
    other_count = 0
    for msg in messages:
        for content in msg.contents:
            if content.emoji_id:
                face_count += 1
            elif content.type.value == "emoji":
                other_count += 1

    return EmojiStatistics(
        face_count=face_count,
        other_emoji_count=other_count,
    )
