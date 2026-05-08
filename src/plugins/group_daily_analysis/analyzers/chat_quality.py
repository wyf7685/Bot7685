"""聊天质量分析器。"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

from ..domain.models import QualityDimension, QualityReview
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class ChatQualityAnalyzer(BaseAnalyzer[QualityReview]):
    data_type = "聊天质量"

    def __init__(self, prompt_template: str | None = None) -> None:
        self._prompt_template = prompt_template

    def get_max_count(self) -> int:
        return 1  # 每次只生成一份质量报告

    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""

        template_str = self._prompt_template
        if not template_str:
            prompt_file = PROMPT_DIR / "chat_quality_analysis.txt"
            if prompt_file.exists():
                template_str = prompt_file.read_text(encoding="utf-8")
            else:
                template_str = _DEFAULT_PROMPT

        tpl = Template(template_str)
        return tpl.safe_substitute(messages_text=messages_text)

    def _try_parse_json(self, text: str) -> list[dict[str, Any]] | None:
        """重写：聊天质量返回单个对象而非数组。"""
        import json

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1
            if lines[-1].strip() == "```":
                end -= 1
            text = "\n".join(lines[start:end]).strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return [data]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return None

    def create_data_object(self, item: dict[str, Any]) -> QualityReview | None:
        title = item.get("title", "").strip()
        subtitle = item.get("subtitle", "").strip()
        summary = item.get("summary", "").strip()

        raw_dims = item.get("dimensions", [])
        if not isinstance(raw_dims, list):
            raw_dims = []

        dimensions: list[QualityDimension] = []
        for d in raw_dims:
            if not isinstance(d, dict):
                continue
            dimensions.append(
                QualityDimension(
                    name=d.get("name", "").strip(),
                    percentage=float(d.get("percentage", 0)),
                    comment=d.get("comment", "").strip(),
                    color=d.get("color", "#607d8b"),
                )
            )

        if not dimensions:
            return None

        return QualityReview(
            title=title or "今日群聊",
            subtitle=subtitle or "",
            dimensions=dimensions,
            summary=summary or "",
        )


_DEFAULT_PROMPT = """\
请分析以下群聊记录，输出一份"聊天质量锐评"。

任务：
1. 将聊天内容划分为 3-6 个高层级抽象维度
2. 为每个维度计算百分比（总和 ≤ 100%）
3. 为每个维度写一句犀利/幽默的点评
4. 给出一句总结性评价

群聊记录格式: [HH:MM] [用户ID]: 消息内容

群聊记录：
${messages_text}

请以纯 JSON 格式返回，不要包含 markdown 代码块标记。

示例格式：
{"title": "今日主题", "subtitle": "副标题", "dimensions": [{"name": "维度名", "percentage": 40, "comment": "点评"}], "summary": "总结"}"""  # noqa: E501
