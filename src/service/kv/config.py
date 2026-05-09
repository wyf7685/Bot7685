from typing import Self

from nonebot import get_plugin_config
from nonebot_plugin_localstore import get_plugin_data_dir
from pydantic import BaseModel, model_validator


class Config(BaseModel):
    kv_store_db_url: str = "<UNSET>"

    @model_validator(mode="after")
    def validate_db_url(self) -> Self:
        if self.kv_store_db_url == "<UNSET>":
            db_path = get_plugin_data_dir().joinpath("kv_cache.db").resolve()
            self.kv_store_db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        return self


plugin_config = get_plugin_config(Config)
