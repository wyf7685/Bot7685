from nonebot import get_plugin_config
from nonebot_plugin_uninfo import Session
from pydantic import BaseModel


class LLMConfig(BaseModel):
    model: str
    endpoint: str
    api_key: str


class PluginConfig(BaseModel):
    enabled: set[str]
    user_threshold: int = 2
    per_user_threshold: int = 8
    trigger_delta: int = 60 * 3
    record_delta: int = 60 * 5
    warning_msg: str = "检测到敏感内容: {reason}"
    llm: LLMConfig

    def enabled_for(self, session: Session) -> bool:
        return not session.scene.is_private and (
            session.scene.id in self.enabled
            or f"{session.adapter.lower()}:{session.scene.id}" in self.enabled
        )


class Config(BaseModel):
    monitor: PluginConfig


config = get_plugin_config(Config).monitor
