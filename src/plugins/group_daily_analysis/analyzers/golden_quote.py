"""金句分析器。"""

from pathlib import Path
from string import Template
from typing import override

from nonebot import logger
from nonebot.utils import escape_tag

from ..domain.models import GoldenQuote
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class GoldenQuoteAnalyzer(BaseAnalyzer[GoldenQuote]):
    data_type = "金句"

    def __init__(self, max_quotes: int = 5, prompt_template: str | None = None) -> None:
        self._max_quotes = max_quotes
        self._prompt_template = prompt_template
        self._id_to_nickname: dict[str, str] = {}
        self.incremental_max_count: int | None = None

    @override
    def get_max_count(self) -> int:
        if self.incremental_max_count is not None:
            return self.incremental_max_count
        return self._max_quotes

    @property
    @override
    def data_object_model(self) -> type[GoldenQuote]:
        return GoldenQuote

    @override
    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages = [msg for msg in messages if 2 <= msg.get_text_length() <= 500]
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""
        self._build_nickname_mapping(messages)

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

    @override
    def process_response(self, response: list[GoldenQuote]) -> list[GoldenQuote]:
        for quote in super().process_response(response):
            if (sender_id := quote.sender.strip().strip("[]")) and (
                nickname := self._lookup_nickname(sender_id)
            ):
                quote.sender = nickname
                quote.user_id = sender_id
            elif (user_id := quote.user_id.strip().strip("[]")) and (
                nickname := self._lookup_nickname(user_id)
            ):
                quote.sender = nickname
                quote.user_id = user_id
            else:
                logger.opt(colors=True).warning(
                    f"[金句分析] 无法匹配 User ID: <y>{escape_tag(quote.user_id)}</>"
                )

        return response


_DEFAULT_PROMPT = """\
请从以下群聊记录中挑选出 ${max_golden_quotes} 句最具冲击力的「金句」。

金句标准：具备颠覆常识的脑洞、逻辑跳脱的表达或强烈反差感的原创内容。

群聊记录格式: [HH:MM] [用户ID]: 消息内容

群聊记录：
${messages_text}

请以纯 JSON 数组格式返回，不要包含 markdown 代码块标记。

示例格式：
[{"content": "金句原文", "sender": "[123456]", "reason": "选择理由"}]"""
