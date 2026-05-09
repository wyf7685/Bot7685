"""用户称号分析器 — 基于预计算的用户活跃统计数据。"""

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import override

from ..domain.incremental import UserActivity
from ..domain.models import UserTitle
from .base import BaseAnalyzer

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


@dataclass(slots=True)
class UserActivityStats(UserActivity):
    """单个用户的活跃统计摘要，用于称号分析 prompt 生成。"""

    @property
    def avg_chars(self) -> float:
        if self.message_count <= 0:
            return 0.0
        return self.char_count / self.message_count

    @property
    def emoji_ratio(self) -> float:
        if self.message_count <= 0:
            return 0.0
        return self.emoji_count / self.message_count

    @property
    def night_message_count(self) -> int:
        return sum(self.hours.get(h, 0) for h in range(6))

    @property
    def night_ratio(self) -> float:
        if self.message_count <= 0:
            return 0.0
        return self.night_message_count / self.message_count

    @property
    def reply_ratio(self) -> float:
        if self.message_count <= 0:
            return 0.0
        return self.reply_count / self.message_count

    @classmethod
    def from_user_activity(cls, activity: UserActivity) -> UserActivityStats:
        return cls(**dataclasses.asdict(activity))

    def format_for_prompt(self) -> str:
        return json.dumps(
            {
                "name": self.nickname,
                "user_id": self.user_id,
                "message_count": self.message_count,
                "avg_chars": round(self.avg_chars, 1),
                "emoji_ratio": round(self.emoji_ratio, 2),
                "night_ratio": round(self.night_ratio, 2),
                "reply_ratio": round(self.reply_ratio, 2),
            },
            ensure_ascii=False,
        )


@dataclass(frozen=True, slots=True)
class UserTitleInput:
    """用户称号分析的输入数据 — 按消息数降序排列的 Top N 用户活跃统计。"""

    users: list[UserActivityStats]

    def __bool__(self) -> bool:
        return bool(self.users)

    def to_prompt_text(self) -> str:
        return "\n".join(u.format_for_prompt() for u in self.users)

    @classmethod
    def from_user_activities(
        cls,
        activities: dict[str, UserActivity],
        max_users: int = 10,
    ) -> UserTitleInput:
        sorted_users = sorted(
            activities.values(), key=lambda u: u.message_count, reverse=True
        )[:max_users]
        return cls(users=list(map(UserActivityStats.from_user_activity, sorted_users)))


class UserTitleAnalyzer(BaseAnalyzer[UserTitle, UserTitleInput]):
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
    def build_prompt(self, data: UserTitleInput) -> str:
        users_text = data.to_prompt_text()
        if not users_text:
            return ""

        template_str = self._prompt_template
        if not template_str:
            prompt_file = PROMPT_DIR / "user_title_prompt.txt"
            if prompt_file.exists():
                template_str = prompt_file.read_text(encoding="utf-8")
            else:
                template_str = _DEFAULT_PROMPT

        tpl = Template(template_str)
        return tpl.safe_substitute(
            max_user_titles=self._max_titles,
            users_text=users_text,
        )


_DEFAULT_PROMPT = """\
请为以下群友分配合适的称号和 MBTI 类型。

## 规则：

- 每个人只能有一个称号
- 每个称号只能给一个人

## 可选称号：

- **龙王**: 发言频繁但内容轻松的人
- **技术专家**: 经常讨论技术话题的人
- **夜猫子**: 经常在深夜发言的人
- **表情包军火库**: 经常发表情的人
- **沉默终结者**: 经常开启话题的人
- **评论家**: 平均发言长度很长的人
- **阳角**: 在群里很有影响力的人
- **互动达人**: 经常回复别人的人
- *...（你可以自行进行拓展添加）*

## 用户数据：

${users_text}

---

### 返回格式示例：

```json
[
  {{
    "name": "用户名",
    "user_id": "123456789",
    "title": "称号",
    "mbti": "MBTI类型",
    "reason": "获得此称号的原因"
  }}
]
```

**注意**：请以纯 JSON 格式返回，不要包含 markdown 代码块标记。"""
