"""LLM 调用封装 — 桥接全局 LLM 服务与插件配置。"""

from __future__ import annotations

from nonebot.log import logger
from nonebot.utils import escape_tag

from src.service.llm import (
    SystemMessage,
    UserMessage,
    get_llm_client,
)
from src.service.llm.exceptions import LLMServiceError


async def call_llm(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str | None:
    """调用 LLM 并返回文本结果。

    Args:
        prompt: 用户提示词
        system_prompt: 可选的系统提示词
        temperature: 温度参数
        max_tokens: 最大 token 数

    Returns:
        LLM 返回的文本，失败时返回 None
    """
    try:
        client = get_llm_client()

        messages = []
        if system_prompt:
            messages.append(SystemMessage(system_prompt))
        messages.append(UserMessage(prompt))

        return await client.chat_completion(
            *messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except LLMServiceError as e:
        logger.opt(colors=True).error(f"LLM 调用失败: {escape_tag(str(e))}")
        return None
