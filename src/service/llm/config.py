from typing import Self

from nonebot import get_plugin_config
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_validator,
    model_validator,
)

from .models import ModelCapabilities


class _FrozenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EndpointConfig(_FrozenConfig):
    """Connection settings shared by one or more model aliases."""

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


class ModelConfig(_FrozenConfig):
    """A model ID and its endpoint-local execution policy."""

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


class LLMConfig(_FrozenConfig):
    """Validated endpoint, model, and default-model registry configuration."""

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


class _RootConfig(BaseModel):
    llm: LLMConfig = Field(description="LLM service configuration")


def get_llm_config() -> LLMConfig:
    return get_plugin_config(_RootConfig).llm
