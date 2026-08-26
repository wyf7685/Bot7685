"""Safe, normalized LLM service errors."""

from enum import StrEnum


class LLMErrorCategory(StrEnum):
    CONFIGURATION = "configuration"
    CAPABILITY = "capability"
    AUTHENTICATION = "authentication"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PROVIDER = "provider"
    INVALID_RESPONSE = "invalid_response"
    STRUCTURED_OUTPUT = "structured_output"
    TOOL = "tool"
    LIMITS = "limits"


class LLMServiceError(Exception):
    """Expected LLM failure carrying only safe routing metadata."""

    def __init__(
        self,
        *,
        category: LLMErrorCategory,
        model_alias: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        self.category = category
        self.model_alias = model_alias
        self.cause = cause
        message = f"LLM service error: {category.value}"
        if model_alias is not None:
            message += f" (model={model_alias})"
        super().__init__(message)
        if cause is not None:
            self.__cause__ = cause


class LLMConfigurationError(LLMServiceError):
    def __init__(
        self,
        *,
        model_alias: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            category=LLMErrorCategory.CONFIGURATION,
            model_alias=model_alias,
            cause=cause,
        )


class LLMCapabilityError(LLMServiceError):
    def __init__(
        self,
        *,
        model_alias: str,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(
            category=LLMErrorCategory.CAPABILITY,
            model_alias=model_alias,
            cause=cause,
        )


class LLMModelSelectionError(ValueError):
    """Safe validation error for administrative model selection."""


class LLMRunError(LLMServiceError):
    def __init__(
        self,
        *,
        category: LLMErrorCategory,
        model_alias: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        if category in {
            LLMErrorCategory.CONFIGURATION,
            LLMErrorCategory.CAPABILITY,
        }:
            raise ValueError("use the specific configuration or capability error")
        super().__init__(category=category, model_alias=model_alias, cause=cause)
