"""OpenAI 兼容的 LLM 服务。"""

from .client import LLMClient
from .config import LLMConfig
from .exceptions import (
    CircuitBreakerOpenError,
    LLMClientNotInitializedError,
    LLMJSONParseError,
    LLMRequestError,
    LLMResponseError,
    LLMRetriesExhaustedError,
    LLMServiceError,
)
from .schema import (
    AssistantMessage,
    Message,
    SystemMessage,
    TokenUsage,
    UserMessage,
    dump_messages,
)

__all__ = [
    "AssistantMessage",
    "CircuitBreakerOpenError",
    "LLMClient",
    "LLMClientNotInitializedError",
    "LLMConfig",
    "LLMJSONParseError",
    "LLMRequestError",
    "LLMResponseError",
    "LLMRetriesExhaustedError",
    "LLMServiceError",
    "Message",
    "SystemMessage",
    "TokenUsage",
    "UserMessage",
    "dump_messages",
    "get_llm_client",
    "init_llm_client",
]

_client: LLMClient | None = None


def init_llm_client(config: LLMConfig) -> LLMClient:
    """初始化全局 LLM 客户端（通常在 on_startup 中调用）。"""
    global _client
    _client = LLMClient(config)
    return _client


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端实例。

    Raises:
        LLMClientNotInitializedError: 如果客户端尚未初始化
    """
    if _client is None:
        raise LLMClientNotInitializedError(
            "LLM 客户端尚未初始化，请先调用 init_llm_client()"
        )
    return _client
