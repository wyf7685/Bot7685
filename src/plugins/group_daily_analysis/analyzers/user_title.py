"""用户称号分析器。"""

from pathlib import Path
from string import Template
from typing import override

from ..domain.models import UserTitle
from ..domain.value_objects import UnifiedMessage
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class UserTitleAnalyzer(BaseAnalyzer[UserTitle]):
    data_type = "用户称号"

    def __init__(self, max_titles: int = 8, prompt_template: str | None = None) -> None:
        self._max_titles = max_titles
        self._prompt_template = prompt_template

    @override
    def get_max_count(self) -> int:
        return self._max_titles

    @property
    @override
    def data_object_model(self) -> type[UserTitle]:
        return UserTitle

    @override
    def build_prompt(self, messages: list[UnifiedMessage]) -> str:
        messages_text = self.format_messages_for_prompt(messages)
        if not messages_text:
            return ""

        template_str = self._prompt_template
        if not template_str:
            prompt_file = PROMPT_DIR / "user_title_analysis.txt"
            if prompt_file.exists():
                template_str = prompt_file.read_text(encoding="utf-8")
            else:
                template_str = _DEFAULT_PROMPT

        tpl = Template(template_str)
        return tpl.safe_substitute(
            max_titles=self._max_titles,
            messages_text=messages_text,
        )


_DEFAULT_PROMPT = """\
请为以下群友分配合适的称号和 MBTI 类型。

规则：每个人只能有一个称号，每个称号只能给一个人。

可选称号：
- 龙王: 发言频繁但内容轻松的人
- 技术专家: 经常讨论技术话题的人
- 夜猫子: 经常在深夜发言的人
- 表情包军火库: 经常发表情的人
- 沉默终结者: 经常开启话题的人
- 评论家: 平均发言长度很长的人
- 阳角: 在群里很有影响力的人
- 互动达人: 经常回复别人的人

群聊记录格式: [HH:MM] [用户ID]: 消息内容

群聊记录：
${messages_text}

请以纯 JSON 数组格式返回，不要包含 markdown 代码块标记。

示例格式：
[{"name": "用户名", "user_id": "123456", "title": "称号", "mbti": "INTJ", "reason": "原因"}]"""  # noqa: E501
