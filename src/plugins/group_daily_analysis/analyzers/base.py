"""基础分析器 — 定义通用分析流程。"""

from abc import ABC, abstractmethod
from typing import ClassVar, LiteralString, cast

from nonebot.log import logger

from src.service.llm import TokenUsage

from ..domain.value_objects import UnifiedMessage
from ..services.llm_service import call_llm


class BaseAnalyzer[
    DataObject,
    InputData = list[UnifiedMessage],
    Response = list[DataObject],
](ABC):
    """分析器基类。

    子类需实现:
    - data_type: 数据类型标识（用于日志）
    - max_count(): 最大提取数量
    - build_prompt(): 构建 LLM 提示词
    - data_object_model: Pydantic 模型（返回类型）
    - response_model: Pydantic 模型（用于结构化输出），默认 list[data_object_model]
    """

    data_type: ClassVar[LiteralString] = "unknown"

    @abstractmethod
    def get_max_count(self) -> int: ...

    @abstractmethod
    def build_prompt(self, data: InputData, /) -> str: ...

    @property
    @abstractmethod
    def data_object_model(self) -> type[DataObject]: ...

    @property
    def response_model(self) -> type[Response]:
        return cast("type[Response]", list[self.data_object_model])

    def process_response(self, response: Response) -> list[DataObject]:
        return (
            list(response)[: self.get_max_count()] if isinstance(response, list) else []
        )

    def _build_nickname_mapping(self, messages: list[UnifiedMessage]) -> None:
        self._id_to_nickname = {
            msg.sender_id: msg.display_name for msg in messages if msg.sender_id
        }

    def _lookup_nickname(self, user_id: str) -> str | None:
        if not hasattr(self, "_id_to_nickname"):
            return None
        return self._id_to_nickname.get(user_id)

    async def analyze(
        self,
        data: InputData,
        system_prompt: str | None = None,
    ) -> tuple[list[DataObject], TokenUsage]:
        """执行分析流程。

        Args:
            data: 输入数据，具体类型由子类的 build_prompt 决定
            system_prompt: 可选的系统提示词
        """

        logger.opt(colors=True).info(f"开始 <y>{self.data_type}</> 分析")

        prompt = self.build_prompt(data)
        if not prompt or not prompt.strip():
            logger.warning(f"{self.data_type} 分析: prompt 为空，跳过")
            return [], TokenUsage()

        response, token_usage = await call_llm(
            self.response_model, prompt, system_prompt
        )
        if not response:
            logger.error(f"{self.data_type} 分析: LLM 未返回结果")
            return [], token_usage

        objects = self.process_response(response)

        logger.opt(colors=True).info(
            f"{self.data_type} 分析完成，获得 <g>{len(objects)}</> 条结果"
        )
        return objects, token_usage

    @staticmethod
    def format_messages_for_prompt(messages: list[UnifiedMessage]) -> str:
        """将消息列表格式化为 prompt 可用的文本。"""
        lines: list[str] = []
        for msg in messages:
            if not msg.has_text:
                continue
            time_str = msg.get_datetime().strftime("%H:%M")
            lines.append(f"[{time_str}] [{msg.sender_id}]: {msg.text_content}")
        return "\n".join(lines)
