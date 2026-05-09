from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import BaseModel, field_validator


class Config(BaseModel):
    kv_cache_db_url: str = "<UNSET>"

    @field_validator("kv_cache_db_url", mode="before")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if v == "<UNSET>":
            db_path = get_plugin_data_dir().joinpath("kv_cache.db").resolve()
            return f"sqlite+aiosqlite:///{db_path.as_posix()}"
        return v


plugin_config = get_plugin_config(Config)
