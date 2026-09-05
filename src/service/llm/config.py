from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    FieldSerializationInfo,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)

from .models import ModelCapabilities, ReasoningEffort

_OPENAI_REASONING_EFFORTS: frozenset[ReasoningEffort] = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)
_ANTHROPIC_REASONING_EFFORTS: frozenset[ReasoningEffort] = frozenset(
    {"none", "low", "medium", "high", "xhigh", "max"}
)


class _FrozenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EndpointProtocol(StrEnum):
    OPENAI_COMPLETIONS = "openai-completions"
    OPENAI_RESPONSES = "openai-responses"
    ANTHROPIC_MESSAGES = "anthropic-messages"


class AnthropicThinkingConfig(_FrozenConfig):
    """Anthropic Messages thinking configuration stored with one model."""

    type: Literal["disabled", "adaptive", "enabled"]
    budget_tokens: int | None = Field(default=None, ge=1024)

    @model_validator(mode="after")
    def validate_budget(self) -> Self:
        if self.type == "enabled":
            if self.budget_tokens is None:
                raise ValueError("enabled Anthropic thinking requires budget_tokens")
        elif self.budget_tokens is not None:
            raise ValueError(
                "budget_tokens is only valid for enabled Anthropic thinking"
            )
        return self


class EndpointConfig(_FrozenConfig):
    """Connection settings shared by one or more model aliases."""

    protocol: EndpointProtocol
    base_url: AnyHttpUrl
    api_key: SecretStr
    timeout_seconds: PositiveFloat = 60.0
    max_retries: NonNegativeInt = 1

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("api_key must not be empty")
        return SecretStr(secret)

    @field_serializer("api_key", when_used="json")
    def serialize_api_key(
        self,
        value: SecretStr,
        info: FieldSerializationInfo,
    ) -> str:
        context = info.context
        if isinstance(context, dict) and context.get("persist_secrets") is True:
            return value.get_secret_value()
        return str(value)


class ModelConfig(_FrozenConfig):
    """A model ID and its endpoint-local execution policy."""

    endpoint: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_concurrent: PositiveInt = 1
    default_max_output_tokens: PositiveInt | None = None
    capabilities: ModelCapabilities
    anthropic_thinking: AnthropicThinkingConfig | None = None
    selectable: bool = True

    @field_validator("endpoint", "model")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value

    def validate_for_protocol(self, protocol: EndpointProtocol) -> None:
        """Reject model settings that the selected endpoint cannot express."""
        if not isinstance(protocol, EndpointProtocol):
            raise TypeError("protocol must be EndpointProtocol")

        reasoning_efforts = set(self.capabilities.reasoning_efforts)
        if protocol is EndpointProtocol.ANTHROPIC_MESSAGES:
            if "json_object" in self.capabilities.structured_output_modes:
                raise ValueError("Anthropic Messages does not support json_object mode")
            unsupported = reasoning_efforts - _ANTHROPIC_REASONING_EFFORTS
            if unsupported:
                values = ", ".join(sorted(unsupported))
                raise ValueError(
                    f"Anthropic Messages cannot express reasoning efforts: {values}"
                )
            if self.default_max_output_tokens is None:
                raise ValueError(
                    "Anthropic Messages requires default_max_output_tokens"
                )
            thinking = self.anthropic_thinking
            if thinking is not None:
                if thinking.type == "disabled" and any(
                    effort != "none" for effort in reasoning_efforts
                ):
                    raise ValueError(
                        "disabled Anthropic thinking contradicts positive reasoning "
                        "efforts"
                    )
                if (
                    thinking.type == "enabled"
                    and thinking.budget_tokens is not None
                    and thinking.budget_tokens >= self.default_max_output_tokens
                ):
                    raise ValueError(
                        "Anthropic thinking budget_tokens must be less than "
                        "default_max_output_tokens"
                    )
            return

        if self.anthropic_thinking is not None:
            raise ValueError("anthropic_thinking is only valid for Anthropic Messages")
        unsupported = reasoning_efforts - _OPENAI_REASONING_EFFORTS
        if unsupported:
            values = ", ".join(sorted(unsupported))
            raise ValueError(
                f"OpenAI protocols cannot express reasoning efforts: {values}"
            )


class LLMConfig(_FrozenConfig):
    """Validated endpoint, model, and active-model registry configuration."""

    active_model: str = Field(min_length=1)
    endpoints: dict[str, EndpointConfig] = Field(min_length=1)
    models: dict[str, ModelConfig] = Field(min_length=1)

    @field_validator("active_model")
    @classmethod
    def validate_active_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("active_model must not be empty")
        return value

    @field_validator("endpoints", "models")
    @classmethod
    def normalize_aliases(cls, value: dict[str, object]) -> dict[str, object]:
        normalized: dict[str, object] = {}
        for raw_alias, item in value.items():
            alias = raw_alias.strip()
            if not alias:
                raise ValueError("aliases must not be empty")
            if alias in normalized:
                raise ValueError("aliases must be unique after normalization")
            normalized[alias] = item
        return normalized

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        active = self.models.get(self.active_model)
        if active is None:
            raise ValueError(
                f"active_model references unknown model alias {self.active_model!r}"
            )
        if not active.selectable:
            raise ValueError("active_model must be selectable")

        missing_endpoints = {
            model.endpoint
            for model in self.models.values()
            if model.endpoint not in self.endpoints
        }
        if missing_endpoints:
            missing = ", ".join(sorted(missing_endpoints))
            raise ValueError(f"models reference unknown endpoints: {missing}")

        incompatible: list[str] = []
        for alias, model in self.models.items():
            protocol = self.endpoints[model.endpoint].protocol
            try:
                model.validate_for_protocol(protocol)
            except ValueError as error:
                incompatible.append(f"{alias}: {error}")
        if incompatible:
            raise ValueError(
                "incompatible model configuration: " + "; ".join(incompatible)
            )
        return self


__all__ = [
    "AnthropicThinkingConfig",
    "EndpointConfig",
    "EndpointProtocol",
    "LLMConfig",
    "ModelConfig",
]
