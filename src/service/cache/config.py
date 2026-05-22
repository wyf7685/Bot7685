from nonebot import get_plugin_config
from pydantic import BaseModel, SecretStr


class CacheConfig(BaseModel):
    cache_prefix: str = "bot7685"
    cache_default_ttl: float = 3600.0
    cache_pickle_protocol: int | None = None


cache_config = get_plugin_config(CacheConfig)


class RedisConfig(BaseModel):
    host: str
    port: int = 6379
    db: int = 0
    password: SecretStr | None = None

    @property
    def password_value(self) -> str | None:
        return self.password.get_secret_value() if self.password else None


class Config(BaseModel):
    redis: RedisConfig | None = None


def get_redis_config() -> RedisConfig | None:
    return get_plugin_config(Config).redis
