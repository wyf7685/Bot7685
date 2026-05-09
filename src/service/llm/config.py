from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class LLMConfig(BaseModel):
    """OpenAI 兼容 API 配置"""

    base_url: str = Field(description="API 基础 URL，不含 /chat/completions 后缀")
    api_key: str = Field(description="API Key")
    model: str = Field(default="gpt-4o", description="模型名称")
    timeout: float = Field(default=120.0, description="请求超时时间（秒）")
    max_retries: int = Field(default=3, description="最大重试次数")
    retry_backoff: float = Field(default=1.0, description="重试退避基数（秒）")
    max_concurrent: int = Field(default=5, description="最大并发请求数")


class Config(BaseModel):
    llm: LLMConfig = Field(description="LLM 服务配置")


service_config = get_plugin_config(Config).llm
