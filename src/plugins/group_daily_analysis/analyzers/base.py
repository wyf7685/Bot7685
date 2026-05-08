"""基础分析器 — 定义通用分析流程。"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from nonebot.log import logger

from ..domain.models import TokenUsage
from ..domain.value_objects import UnifiedMessage


class BaseAnalyzer[TDataObject](ABC):
    """分析器基类。

    子类需实现:
    - data_type: 数据类型标识（用于日志）
    - max_count(): 最大提取数量
    - build_prompt(): 构建 LLM 提示词
    - create_data_object(): 从 dict 构造领域对象
    - response_model: Pydantic 模型（用于结构化输出）
    """

    data_type: str = "unknown"

    @abstractmethod
    def get_max_count(self) -> int: ...

    @abstractmethod
    def build_prompt(self, messages: list[UnifiedMessage]) -> str: ...

    @abstractmethod
    def create_data_object(self, item: dict[str, Any]) -> TDataObject | None: ...

    @property
    def response_model(self) -> type | None:
        """Pydantic 模型，子类可重写以启用结构化输出。"""
        return None

    async def analyze(
        self,
        messages: list[UnifiedMessage],
        system_prompt: str | None = None,
    ) -> tuple[list[TDataObject], TokenUsage]:
        """执行分析流程。"""
        from ..services.llm_service import call_llm

        logger.opt(colors=True).info(
            f"开始 <y>{self.data_type}</> 分析，输入 <g>{len(messages)}</> 条消息"
        )

        prompt = self.build_prompt(messages)
        if not prompt or not prompt.strip():
            logger.warning(f"{self.data_type} 分析: prompt 为空，跳过")
            return [], TokenUsage()

        # 调用 LLM
        result_text = await call_llm(prompt, system_prompt=system_prompt)
        if not result_text:
            logger.error(f"{self.data_type} 分析: LLM 返回空结果")
            return [], TokenUsage()

        # 尝试解析 JSON
        parsed = self._try_parse_json(result_text)
        if parsed is None:
            # 正则降级
            parsed = self._extract_with_regex(result_text)

        if not parsed:
            logger.error(f"{self.data_type} 分析: JSON 解析与正则降级均失败")
            return [], TokenUsage()

        # 构造数据对象
        objects: list[TDataObject] = []
        for item in parsed[: self.get_max_count()]:
            obj = self.create_data_object(item)
            if obj is not None:
                objects.append(obj)

        logger.opt(colors=True).info(
            f"{self.data_type} 分析完成，获得 <g>{len(objects)}</> 条结果"
        )
        return objects, TokenUsage()

    def _try_parse_json(self, text: str) -> list[dict[str, Any]] | None:
        """尝试从 LLM 返回文本中解析 JSON 数组。"""
        text = text.strip()

        # 去除 markdown 包裹
        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1
            if lines[-1].strip() == "```":
                end -= 1
            text = "\n".join(lines[start:end]).strip()

        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return [data]
        except json.JSONDecodeError:
            pass
        return None

    def _extract_with_regex(self, _text: str, /) -> list[dict[str, Any]]:
        """正则降级提取（子类可重写）。"""
        return []

    @staticmethod
    def format_messages_for_prompt(
        messages: list[UnifiedMessage],
    ) -> str:
        """将消息列表格式化为 prompt 可用的文本。"""
        lines: list[str] = []
        for msg in messages:
            if not msg.has_text():
                continue
            time_str = msg.get_datetime().strftime("%H:%M")
            lines.append(f"[{time_str}] [{msg.sender_id}]: {msg.text_content}")
        return "\n".join(lines)
