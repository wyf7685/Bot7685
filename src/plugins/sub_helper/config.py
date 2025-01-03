from pathlib import Path

from nonebot.plugin import get_plugin_config
from pydantic import BaseModel, ConfigDict, SecretStr


class AliConfig(BaseModel):
    class _Credential(BaseModel):
        access_key_id: SecretStr
        access_key_secret: SecretStr

    credential: _Credential
    region_id: str
    template_id: str
    instance_name: str


class TencentConfig(BaseModel):
    class _Credential(BaseModel):
        secret_id: SecretStr
        secret_key: SecretStr

    credential: _Credential
    domain: str
    sub_domain: str


class SSHConfig(BaseModel):
    port: int
    username: str
    private_key: Path
    sub_helper_data: Path
    update_file: str
    update_eval: str


class SubConfig(BaseModel):
    class _Inner(BaseModel):
        model_config = ConfigDict(extra="allow")

    d: _Inner
    u: Path
    inner: str
    outer: str


class PluginConfig(BaseModel):
    ali: AliConfig
    tencent: TencentConfig
    ssh: SSHConfig
    sub: SubConfig


class Config(BaseModel):
    sub_helper: PluginConfig


plugin_config = get_plugin_config(Config).sub_helper
