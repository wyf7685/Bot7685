"""增量合并领域服务。

负责将 IncrementalBatch 列表合并为 IncrementalState，
以及将 IncrementalState 累积数据转换为现有实体类型，
以便复用现有的报告生成器和分发器。
"""

import time as time_mod
from typing import TYPE_CHECKING

from nonebot.log import logger

from ..domain.incremental import (
    IncrementalAnalysisResult,
    IncrementalBatch,
    IncrementalState,
    UserActivity,
)
from ..domain.models import ActivityVisualization, GroupStatistics, UserTitle

if TYPE_CHECKING:
    from _typeshed import SupportsAdd


class IncrementalMergeService:
    """增量合并服务。

    将滑动窗口内的多个批次数据合并为报告所需的数据结构，
    确保增量模式下生成的最终报告与传统单次分析报告格式完全一致。
    """

    @staticmethod
    def merge_dict[K, V: SupportsAdd](
        a: dict[K, V], b: dict[K, V], default: V
    ) -> dict[K, V]:
        return {
            key: a.get(key, default) + b.get(key, default) for key in set(a) | set(b)
        }

    def merge_batches(
        self,
        batches: list[IncrementalBatch],
        window_start: float,
        window_end: float,
    ) -> IncrementalState:
        state = IncrementalState(
            group_id=batches[0].group_id if batches else "",
            window_start=window_start,
            window_end=window_end,
            total_analysis_count=len(batches),
            created_at=window_start,
            updated_at=time_mod.time(),
        )

        for batch in batches:
            state.total_message_count += batch.messages_count
            state.total_character_count += batch.characters_count

            # 合并每小时消息分布
            state.hourly_message_counts = self.merge_dict(
                state.hourly_message_counts, batch.hourly_msg_counts, 0
            )

            # 合并每小时字符分布
            state.hourly_character_counts = self.merge_dict(
                state.hourly_character_counts, batch.hourly_char_counts, 0
            )

            # 合并用户统计
            for user_id, stats in batch.user_stats.items():
                if user_id not in state.user_activities:
                    state.user_activities[user_id] = UserActivity(
                        user_id, stats.nickname
                    )
                state.user_activities[user_id] += stats

            # 合并表情统计
            state.emoji_counts += batch.emoji_stats

            # 合并话题（去重）
            for topic in batch.topics:
                if not state.is_duplicate_topic(topic):
                    state.topics.append(topic)

            # 合并金句（去重）
            for quote in batch.golden_quotes:
                if not state.is_duplicate_quote(quote):
                    state.golden_quotes.append(quote)

            # 累加 token 消耗
            state.total_token_usage += batch.token_usage

            # 合并参与者 ID
            state.all_participant_ids.update(batch.participant_ids)

            # 收集质量锐评
            if batch.chat_quality_review:
                state.all_quality_reviews.append(batch.chat_quality_review)

            # 记录最后分析消息时间戳
            if batch.last_message_timestamp > state.last_analyzed_message_timestamp:
                state.last_analyzed_message_timestamp = batch.last_message_timestamp
                if batch.chat_quality_review:
                    state.chat_quality_review = batch.chat_quality_review

        logger.info(
            f"合并批次完成: 群={state.group_id}, "
            f"窗口={state.get_window_date_str()}, "
            f"批次数={len(batches)}, "
            f"总消息={state.total_message_count}, "
            f"话题={len(state.topics)}, 金句={len(state.golden_quotes)}"
        )

        return state

    def build_final_statistics(self, state: IncrementalState) -> GroupStatistics:
        hourly_activity = {
            hour: state.hourly_message_counts.get(hour, 0) for hour in range(24)
        }
        activity_visualization = ActivityVisualization(
            hourly_activity=hourly_activity,
            daily_activity={state.get_window_date_str(): state.total_message_count},
            user_activity_ranking=state.get_user_activity_ranking(10),
            peak_hours=state.get_peak_hours(3),
            activity_heatmap_data={},
        )
        return GroupStatistics(
            message_count=state.total_message_count,
            total_characters=state.total_character_count,
            participant_count=len(state.all_participant_ids),
            most_active_period=state.get_most_active_period(),
            golden_quotes=state.golden_quotes,
            emoji_count=state.emoji_counts.total_emoji_count,
            emoji_statistics=state.emoji_counts,
            activity_visualization=activity_visualization,
            token_usage=state.total_token_usage,
            chat_quality_review=state.chat_quality_review,
        )

    def build_analysis_result(
        self,
        state: IncrementalState,
        user_titles: list[UserTitle] | None = None,
    ) -> IncrementalAnalysisResult:
        statistics = self.build_final_statistics(state)
        return IncrementalAnalysisResult(
            statistics=statistics,
            topics=state.topics,
            golden_quotes=statistics.golden_quotes,
            user_titles=user_titles or [],
            user_analysis=state.user_activities,
            chat_quality_review=statistics.chat_quality_review,
        )
