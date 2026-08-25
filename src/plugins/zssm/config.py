from typing import Literal, Self

from pydantic import (
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


class _FrozenConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ImagesConfig(_FrozenConfig):
    max_count: PositiveInt = 2
    max_source_bytes: PositiveInt = 20 * 1024 * 1024
    max_payload_bytes: PositiveInt = 5 * 1024 * 1024
    max_pixels: PositiveInt = 40_000_000
    max_edge_px: PositiveInt = 4096
    jpeg_quality: int = Field(default=85, ge=1, le=100)
    max_parallel: PositiveInt = 2
    vision_output_chars: PositiveInt = 2000

    @model_validator(mode="after")
    def validate_limits(self) -> Self:
        if self.max_payload_bytes > self.max_source_bytes:
            raise ValueError("max_payload_bytes must not exceed max_source_bytes")
        if self.max_parallel > self.max_count:
            raise ValueError("max_parallel must not exceed max_count")
        return self


class WebSearchConfig(_FrozenConfig):
    backend: Literal["brave", "ddgs", "tavily"] = "brave"
    timeout_seconds: PositiveFloat = 8.0
    max_results: int = Field(default=8, ge=1, le=8)
    safe_search: Literal["off", "moderate", "strict"] = "moderate"
    brave_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    ddgs_backend: str = Field(default="duckduckgo", min_length=1)
    ddgs_max_parallel: PositiveInt = 2

    @field_validator("brave_api_key")
    @classmethod
    def validate_brave_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("brave_api_key must not be empty")
        return value

    @field_validator("tavily_api_key")
    @classmethod
    def validate_tavily_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("tavily_api_key must not be empty")
        return value

    @field_validator("ddgs_backend")
    @classmethod
    def validate_ddgs_backend(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("ddgs_backend must not be empty")
        if value.casefold() == "auto":
            raise ValueError("ddgs_backend must be a fixed named backend")
        return value

    @model_validator(mode="after")
    def validate_backend_credentials(self) -> Self:
        if self.backend == "brave" and self.brave_api_key is None:
            raise ValueError("brave_api_key is required when backend is 'brave'")
        if self.backend == "tavily" and self.tavily_api_key is None:
            raise ValueError("tavily_api_key is required when backend is 'tavily'")
        return self


class FetchPageConfig(_FrozenConfig):
    respect_robots: bool = True
    max_redirects: NonNegativeInt = 5
    max_wire_bytes: PositiveInt = 2 * 1024 * 1024
    max_decoded_bytes: PositiveInt = 8 * 1024 * 1024
    max_expansion_ratio: PositiveFloat = 20.0
    max_text_chars: PositiveInt = 100_000
    total_timeout_seconds: PositiveFloat = 15.0
    allowed_content_types: tuple[str, ...] = (
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "text/markdown",
    )

    @field_validator("allowed_content_types")
    @classmethod
    def validate_content_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(content_type.strip().lower() for content_type in value)
        if not normalized or any(not content_type for content_type in normalized):
            raise ValueError("allowed_content_types must not be empty")
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_content_types must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_byte_limits(self) -> Self:
        if self.max_wire_bytes > self.max_decoded_bytes:
            raise ValueError("max_wire_bytes must not exceed max_decoded_bytes")
        return self


class HistoryConfig(_FrozenConfig):
    default_count: int = Field(default=20, ge=1, le=50)
    max_count: int = Field(default=50, ge=1, le=50)
    default_lookback_minutes: int = Field(default=120, ge=1, le=1440)
    max_lookback_minutes: int = Field(default=1440, ge=1, le=1440)
    max_message_bytes: PositiveInt = 2048
    max_result_bytes: PositiveInt = 16_384
    max_search_chars: int = Field(default=128, ge=1, le=128)

    @model_validator(mode="after")
    def validate_defaults(self) -> Self:
        if self.default_count > self.max_count:
            raise ValueError("default_count must not exceed max_count")
        if self.default_lookback_minutes > self.max_lookback_minutes:
            raise ValueError(
                "default_lookback_minutes must not exceed max_lookback_minutes"
            )
        if self.max_message_bytes > self.max_result_bytes:
            raise ValueError("max_message_bytes must not exceed max_result_bytes")
        return self


class ForwardsConfig(_FrozenConfig):
    max_references: PositiveInt = 4
    max_nodes: PositiveInt = 30
    max_depth: int = Field(default=2, ge=1, le=4)
    max_segments: PositiveInt = 300
    max_text_chars: PositiveInt = 20_000
    fetch_timeout_seconds: PositiveFloat = 10.0


class ParticipantsConfig(_FrozenConfig):
    max_per_tool_call: int = Field(default=20, ge=1, le=20)
    max_parallel_lookups: PositiveInt = 8
    display_name_chars: PositiveInt = 64


class RenderingConfig(_FrozenConfig):
    node_name: str = Field(default="ZSSM", min_length=1)
    max_node_chars: int = Field(default=16_000, ge=1, le=16_000)
    include_sources: bool = True
    include_tool_trace: bool = True

    @field_validator("node_name")
    @classmethod
    def validate_node_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("node_name must not be empty")
        return value


class ZssmConfig(_FrozenConfig):
    default_model: str = Field(default="deepseek", min_length=1)
    selectable_models: tuple[str, ...] = ("deepseek", "gpt")
    vision_model: str = Field(default="mimo-vision", min_length=1)
    max_concurrent_runs: PositiveInt = 2
    max_agent_model_calls: PositiveInt = 8
    max_agent_tool_calls: PositiveInt = 16
    max_agent_parallel_tools: PositiveInt = 4
    agent_timeout_seconds: PositiveFloat = 120.0
    max_output_tokens: PositiveInt = 2000
    images: ImagesConfig = Field(default_factory=ImagesConfig)
    forwards: ForwardsConfig = Field(default_factory=ForwardsConfig)
    web_search: WebSearchConfig
    fetch_page: FetchPageConfig = Field(default_factory=FetchPageConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    participants: ParticipantsConfig = Field(default_factory=ParticipantsConfig)
    rendering: RenderingConfig = Field(default_factory=RenderingConfig)

    @field_validator("default_model", "vision_model")
    @classmethod
    def validate_model_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("model alias must not be empty")
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

    @model_validator(mode="after")
    def validate_model_selection(self) -> Self:
        if self.default_model not in self.selectable_models:
            raise ValueError("default_model must be selectable")
        if self.vision_model in self.selectable_models:
            raise ValueError("vision_model must not be selectable")
        if self.max_agent_parallel_tools > self.max_agent_tool_calls:
            raise ValueError(
                "max_agent_parallel_tools must not exceed max_agent_tool_calls"
            )
        return self


__all__ = [
    "FetchPageConfig",
    "ForwardsConfig",
    "HistoryConfig",
    "ImagesConfig",
    "ParticipantsConfig",
    "RenderingConfig",
    "WebSearchConfig",
    "ZssmConfig",
]
