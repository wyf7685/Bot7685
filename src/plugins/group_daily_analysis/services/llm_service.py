"""LLM 调用封装 — 桥接全局 LLM 服务与插件配置。"""

from nonebot.log import logger

from src.service.llm.exceptions import LLMServiceError
from src.service.llm.models import ChatInput
from src.service.llm.service import get_llm_service
from src.service.llm.usage import TokenUsage


async def call_llm[T](
    response_model: type[T],
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[T | None, TokenUsage]:
    """调用 LLM 并返回结构化结果及 token 使用情况。

    Args:
        response_model: 结构化输出类型
        prompt: 用户提示词
        system_prompt: 可选的系统提示词
        temperature: 温度参数
        max_tokens: 最大输出 token 数

    Returns:
        结构化输出（失败时为 ``None``）及 token 使用情况
    """
    try:
        result = await get_llm_service().complete_structured(
            ChatInput.from_text(prompt),
            output_type=response_model,
            system_prompt=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
    except LLMServiceError:
        logger.exception("LLM 调用失败")
        return None, TokenUsage()
    else:
        return result.output, result.usage
