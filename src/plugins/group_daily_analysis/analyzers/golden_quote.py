"""金句分析器。"""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import Any

from ..domain.models import GoldenQuote
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class GoldenQuoteAnalyzer(BaseAnalyzer[GoldenQuote]):
    data_type = "金句"

    def __init__(self, max_quotes: int = 5, prompt_template: str | None = None) -> None:
        self._max_quotes = max_quotes
        self._prompt_template = prompt_template

    def get_max_count(self) -> int:
        return self._max_quotes

    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""

        template_str = self._prompt_template
        if not template_str:
            prompt_file = PROMPT_DIR / "golden_quote_analysis.txt"
            if prompt_file.exists():
                template_str = prompt_file.read_text(encoding="utf-8")
            else:
                template_str = _DEFAULT_PROMPT

        tpl = Template(template_str)
        return tpl.safe_substitute(
            max_golden_quotes=self._max_quotes,
            messages_text=messages_text,
        )

    def create_data_object(self, item: dict[str, Any]) -> GoldenQuote | None:
        content = item.get("content", "").strip()
        sender = item.get("sender", "").strip()
        reason = item.get("reason", "").strip()
        if not content:
            return None

        return GoldenQuote(
            content=content,
            sender=sender or "未知",
            reason=reason,
            user_id=item.get("user_id", ""),
        )


_DEFAULT_PROMPT = """\
请从以下群聊记录中挑选出 ${max_golden_quotes} 句最具冲击力的「金句」。

金句标准：具备颠覆常识的脑洞、逻辑跳脱的表达或强烈反差感的原创内容。

群聊记录格式: [HH:MM] [用户ID]: 消息内容

群聊记录：
${messages_text}

请以纯 JSON 数组格式返回，不要包含 markdown 代码块标记。

示例格式：
[{"content": "金句原文", "sender": "[123456]", "reason": "选择理由"}]"""
