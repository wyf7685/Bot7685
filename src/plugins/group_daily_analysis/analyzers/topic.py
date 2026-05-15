"""话题分析器。"""

import dataclasses
import re
from collections.abc import Iterable
from string import Template
from typing import override

from ..config import PROMPT_DIR
from ..domain.models import SummaryTopic
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer


class TopicAnalyzer(BaseAnalyzer[SummaryTopic]):
    data_type = "话题"

    def __init__(self, max_topics: int = 5, prompt_template: str | None = None) -> None:
        self._max_topics = max_topics
        self._prompt_template = prompt_template
        self.incremental_max_count: int | None = None

    @override
    def get_max_count(self) -> int:
        if self.incremental_max_count is not None:
            return self.incremental_max_count
        return self._max_topics

    @property
    @override
    def data_object_model(self) -> type[SummaryTopic]:
        return SummaryTopic

    @override
    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages = list(self._extract_text_messages(messages))
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""
        self._build_nickname_mapping(messages)

        template_str = self._prompt_template
        if not template_str:
            prompt_file = PROMPT_DIR / "topic_analysis.txt"
            if prompt_file.exists():
                template_str = prompt_file.read_text(encoding="utf-8")
            else:
                template_str = _DEFAULT_TOPIC_PROMPT

        tpl = Template(template_str)
        return tpl.safe_substitute(
            max_topics=self._max_topics,
            messages_text=messages_text,
        )

    @override
    def process_response(self, response: list[SummaryTopic]) -> list[SummaryTopic]:
        for topic in super().process_response(response):
            raw_ids = topic.contributors or topic.contributor_ids or []
            resolved = {
                user_id: nickname
                for raw_id in raw_ids
                if (user_id := raw_id.strip().strip("[]"))
                and (nickname := self._lookup_nickname(user_id))
            }

            topic.contributor_ids = list(resolved.keys())
            topic.contributors = list(resolved.values())

        return response

    def _extract_text_messages(
        self, messages: list[UnifiedMessage]
    ) -> Iterable[UnifiedMessage]:
        for msg in messages:
            if text := msg.text_content:
                cleaned_text = text.replace("\n", " ").replace("\r", " ")
                cleaned_text = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", cleaned_text)
                if 2 <= len(text) <= 500:
                    yield UnifiedMessage(
                        **{
                            **{
                                field.name: getattr(msg, field.name)
                                for field in dataclasses.fields(msg)
                            },
                            "text_content": cleaned_text,
                        }
                    )


_DEFAULT_TOPIC_PROMPT = """\
请分析以下群聊记录，提取出最多 ${max_topics} 个主要话题。

对于每个话题，请提供：
1. 话题名称（10字以内）
2. 主要参与者用户ID（最多5人）
3. 话题详细描述（包含关键信息和结论）

群聊记录格式: [HH:MM] [用户ID]: 消息内容

群聊记录：
${messages_text}

请以纯 JSON 数组格式返回，不要包含 markdown 代码块标记。

示例格式：
[{"topic": "话题名称", "contributors": ["123456"], "detail": "详细描述"}]"""
