"""聊天质量分析器。"""

from pathlib import Path
from string import Template
from typing import override

from ..domain.models import QualityReview
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class ChatQualityAnalyzer(BaseAnalyzer[QualityReview, QualityReview]):
    data_type = "聊天质量"

    def __init__(self, prompt_template: str | None = None) -> None:
        self._prompt_template = prompt_template

    @override
    def get_max_count(self) -> int:
        return 1  # 每次只生成一份质量报告

    @property
    @override
    def data_object_model(self) -> type[QualityReview]:
        return QualityReview

    @property
    @override
    def response_model(self) -> type[QualityReview]:
        return QualityReview

    @override
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

    @override
    def process_response(self, response: QualityReview) -> list[QualityReview]:
        # 控制维度占比总和不超过100%
        total_percentage = sum(
            max(0.0, min(100.0, d.percentage)) for d in response.dimensions
        )

        factor = 1.0
        if total_percentage > 100:
            factor = 100.0 / total_percentage
        for d in response.dimensions:
            d.percentage = round(max(0.0, min(100.0, d.percentage)) * factor, 1)

        # 自动分配颜色
        colors = [
            "#607d8b",
            "#2196f3",
            "#f44336",
            "#e91e63",
            "#ff9800",
            "#4caf50",
            "#009688",
            "#9c27b0",
        ]
        response.dimensions = [
            d.with_color(colors[i % len(colors)])
            for i, d in enumerate(response.dimensions)
        ]

        return [response]


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
