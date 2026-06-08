from nonebot import get_plugin_config
from pydantic import BaseModel, SecretStr


class Config(BaseModel):
    pixiv_refresh_token: SecretStr | None = None


plugin_cofig = get_plugin_config(Config)
