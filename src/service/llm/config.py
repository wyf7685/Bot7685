from typing import Self

from nonebot import get_plugin_config
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)

from .models import StructuredOutputMode, validate_structured_output_modes


class EndpointConfig(BaseModel):
    """Connection settings shared by one or more model aliases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_url: AnyHttpUrl
    api_key: SecretStr
    timeout_seconds: PositiveFloat = 60.0
    max_retries: PositiveInt = 1

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("api_key must not be empty")
        return value


class ModelCapabilities(BaseModel):
    """Capabilities declared for a configured model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: bool
    vision: bool
    structured_output_modes: tuple[StructuredOutputMode, ...]
    parallel_tool_calls: bool

    @field_validator("structured_output_modes")
    @classmethod
    def validate_modes(
        cls, value: tuple[StructuredOutputMode, ...]
    ) -> tuple[StructuredOutputMode, ...]:
        validate_structured_output_modes(value)
        return value

    @model_validator(mode="after")
    def validate_tool_capabilities(self) -> Self:
        if self.parallel_tool_calls and not self.tools:
            raise ValueError("parallel_tool_calls requires tools capability")
        return self


class ModelConfig(BaseModel):
    """A model ID and its endpoint-local execution policy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    endpoint: str = Field(min_length=1)
    model: str = Field(min_length=1)
    max_concurrent: PositiveInt = 1
    capabilities: ModelCapabilities

    @field_validator("endpoint", "model")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


class LLMConfig(BaseModel):
    """Validated endpoint, model, and default-model registry configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    default_model: str = Field(min_length=1)
    selectable_models: tuple[str, ...]
    endpoints: dict[str, EndpointConfig] = Field(min_length=1)
    models: dict[str, ModelConfig] = Field(min_length=1)

    @field_validator("default_model")
    @classmethod
    def validate_default_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("default_model must not be empty")
        return value

    @field_validator("selectable_models")
    @classmethod
    def validate_selectable_models(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(alias.strip() for alias in value)
        if not normalized or any(not alias for alias in normalized):
            raise ValueError("selectable_models must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("selectable_models must be unique")
        return normalized

    @field_validator("endpoints", "models")
    @classmethod
    def validate_aliases(cls, value: dict[str, object]) -> dict[str, object]:
        if any(not alias.strip() for alias in value):
            raise ValueError("aliases must not be empty")
        return value

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if self.default_model not in self.models:
            raise ValueError(
                f"default_model references unknown model alias {self.default_model!r}"
            )
        if self.default_model not in self.selectable_models:
            raise ValueError("default_model must be selectable")

        unknown_selectable = set(self.selectable_models).difference(self.models)
        if unknown_selectable:
            missing = ", ".join(sorted(unknown_selectable))
            raise ValueError(f"selectable_models reference unknown models: {missing}")

        missing_endpoints = {
            model.endpoint
            for model in self.models.values()
            if model.endpoint not in self.endpoints
        }
        if missing_endpoints:
            missing = ", ".join(sorted(missing_endpoints))
            raise ValueError(f"models reference unknown endpoints: {missing}")
        return self


class Config(BaseModel):
    llm: LLMConfig = Field(description="LLM service configuration")


service_config = get_plugin_config(Config).llm
