"""OpenAI 兼容的 LLM 服务。"""

from .client import LLMClient
from .config import service_config
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
]

_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    """获取全局 LLM 客户端实例。

    Raises:
        LLMClientNotInitializedError: 如果客户端尚未初始化
    """
    global _client
    if _client is None:
        _client = LLMClient(service_config)

    return _client
