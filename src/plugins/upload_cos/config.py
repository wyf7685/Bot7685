from pydantic import BaseModel
from nonebot import get_plugin_config


class UploadCosConfig(BaseModel):
    secret_id: str
    secret_key: str
    region: str
    bucket: str


class Config(BaseModel):
    cos: UploadCosConfig


config = get_plugin_config(Config).cos
