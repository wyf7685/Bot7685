"""LLM 服务异常体系。"""


class LLMServiceError(Exception):
    """LLM 服务异常基类。"""


class LLMClientNotInitializedError(LLMServiceError):
    """LLM 客户端尚未初始化。"""


class CircuitBreakerOpenError(LLMServiceError):
    """熔断器已打开，拒绝请求。"""


class LLMRequestError(LLMServiceError):
    """LLM API 请求失败（网络错误、超时等）。"""


class LLMResponseError(LLMServiceError):
    """LLM API 返回了非预期的响应（非 200 状态码等）。"""


class LLMRetriesExhaustedError(LLMServiceError):
    """所有重试均已耗尽。"""


class LLMJSONParseError(LLMServiceError):
    """LLM 返回的内容无法解析为 JSON。"""
