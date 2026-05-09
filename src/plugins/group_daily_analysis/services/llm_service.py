"""LLM 调用封装 — 桥接全局 LLM 服务与插件配置。"""

from nonebot.log import logger

from src.service.llm import (
    SystemMessage,
    TokenUsage,
    UserMessage,
    get_llm_client,
)
from src.service.llm.exceptions import LLMServiceError


async def call_llm[T](
    response_model: type[T],
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> tuple[T | None, TokenUsage]:
    """调用 LLM 并返回文本结果。

    Args:
        prompt: 用户提示词
        system_prompt: 可选的系统提示词
        temperature: 温度参数
        max_tokens: 最大 token 数

    Returns:
        tuple[str | None, TokenUsage]: LLM 返回的文本内容和 token 使用情况
    """
    try:
        client = get_llm_client()

        messages = []
        if system_prompt:
            messages.append(SystemMessage(system_prompt))
        messages.append(UserMessage(prompt))

        with client.capture_token_usage() as get_usage:
            content = await client.chat_completion_json(
                *messages,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return content, get_usage()
    except LLMServiceError:
        logger.exception("LLM 调用失败")
        return None, TokenUsage()
