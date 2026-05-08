"""话题分析器。"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template
from typing import Any

from ..domain.models import SummaryTopic
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class TopicAnalyzer(BaseAnalyzer[SummaryTopic]):
    data_type = "话题"

    def __init__(self, max_topics: int = 5, prompt_template: str | None = None) -> None:
        self._max_topics = max_topics
        self._prompt_template = prompt_template

    def get_max_count(self) -> int:
        return self._max_topics

    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""

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

    def create_data_object(self, item: dict[str, Any]) -> SummaryTopic | None:
        topic = item.get("topic", "").strip()
        detail = item.get("detail", "").strip()
        if not topic or not detail:
            return None

        contributors = item.get("contributors", [])
        if not isinstance(contributors, list):
            contributors = ["群友"]
        else:
            contributors = [str(c).strip() for c in contributors if c] or ["群友"]

        return SummaryTopic(
            topic=topic,
            contributors=contributors,
            detail=detail,
            contributor_ids=[str(c) for c in contributors],
        )

    def _extract_with_regex(self, text: str) -> list[dict[str, Any]]:
        """正则降级提取话题。"""
        pattern = r'"topic"\s*:\s*"([^"]*)"'
        topics = re.findall(pattern, text)
        return [
            {"topic": t, "contributors": ["群友"], "detail": t}
            for t in topics[: self._max_topics]
        ]


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
