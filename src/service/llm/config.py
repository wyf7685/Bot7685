from typing import Self

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
    capabilities: ModelCapabilities
    selectable: bool = True

    @field_validator("endpoint", "model")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be empty")
        return value


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
        return self


__all__ = ["EndpointConfig", "LLMConfig", "ModelConfig"]
