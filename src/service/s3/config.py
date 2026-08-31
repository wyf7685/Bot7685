import json
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    FieldSerializationInfo,
    PositiveFloat,
    PositiveInt,
    SecretStr,
    field_serializer,
    field_validator,
    model_validator,
)


class S3Config(BaseModel):
    """Validated connection and object-namespace settings for one S3 bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    access_key_id: SecretStr
    secret_access_key: SecretStr
    region: str
    bucket: str
    endpoint_url: str | None = None
    presign_endpoint_url: str | None = None
    path_style: bool = False
    max_concurrency: PositiveInt = 8
    session_token: SecretStr | None = None
    scheme: Literal["http", "https"] = "https"
    timeout_seconds: PositiveFloat = 30.0
    key_prefix: str = "qbot/upload"

    @field_validator("access_key_id", "secret_access_key")
    @classmethod
    def validate_required_secret(cls, value: SecretStr) -> SecretStr:
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("credential must not be empty")
        return SecretStr(secret)

    @field_validator("session_token")
    @classmethod
    def validate_optional_secret(
        cls,
        value: SecretStr | None,
    ) -> SecretStr | None:
        if value is None:
            return None
        secret = value.get_secret_value().strip()
        if not secret:
            raise ValueError("session_token must not be empty")
        return SecretStr(secret)

    @field_serializer(
        "access_key_id",
        "secret_access_key",
        "session_token",
        when_used="json",
    )
    def serialize_secret(
        self,
        value: SecretStr | None,
        info: FieldSerializationInfo,
    ) -> str | None:
        if value is None:
            return None
        context = info.context
        if isinstance(context, dict) and context.get("persist_secrets") is True:
            return value.get_secret_value()
        return str(value)

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        region = self._required_text(self.region, "region")
        bucket = self._required_text(self.bucket, "bucket")
        endpoint = self._endpoint(self.endpoint_url, "endpoint_url")
        presign_endpoint = self._endpoint(
            self.presign_endpoint_url,
            "presign_endpoint_url",
        )
        prefix = self.key_prefix.strip("/")
        if "\x00" in prefix:
            raise ValueError("key_prefix must not contain NUL")
        if any(part in {".", ".."} for part in prefix.split("/") if part):
            raise ValueError("key_prefix must not contain dot path components")
        object.__setattr__(self, "region", region)
        object.__setattr__(self, "bucket", bucket)
        object.__setattr__(self, "endpoint_url", endpoint)
        object.__setattr__(self, "presign_endpoint_url", presign_endpoint)
        object.__setattr__(self, "key_prefix", prefix)
        return self

    @staticmethod
    def _required_text(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} must not be empty")
        if "\x00" in normalized:
            raise ValueError(f"{name} must not contain NUL")
        return normalized

    @staticmethod
    def _endpoint(value: str | None, name: str) -> str | None:
        if value is None:
            return None
        endpoint = value.strip()
        if not endpoint:
            raise ValueError(f"{name} must not be empty")
        if "\x00" in endpoint:
            raise ValueError(f"{name} must not contain NUL")
        if "://" in endpoint:
            raise ValueError(f"{name} must not include a scheme")
        if "@" in endpoint:
            raise ValueError(f"{name} must not include userinfo")
        if any(char in endpoint for char in "/?#"):
            raise ValueError(f"{name} must not include a path or query")
        return endpoint

    @property
    def namespace_identity(self) -> str:
        return json.dumps(
            {
                "bucket": self.bucket,
                "endpoint_url": self.endpoint_url,
                "key_prefix": self.key_prefix,
                "path_style": self.path_style,
                "region": self.region,
                "scheme": self.scheme,
            },
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )


__all__ = ["S3Config"]
