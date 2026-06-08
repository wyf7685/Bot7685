from nonebot import get_plugin_config
from pydantic import BaseModel, SecretStr


class UploadCosConfig(BaseModel):
    secret_id: SecretStr
    secret_key: SecretStr
    region: str
    bucket: str
    is_internal: bool


class Config(BaseModel):
    cos: UploadCosConfig


config = get_plugin_config(Config).cos
