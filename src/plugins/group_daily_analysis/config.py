from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class LLMSettings(BaseModel):
    """LLM 相关配置"""

    retries: int = Field(default=2, description="LLM 请求重试次数")
    backoff: int = Field(default=2, description="重试退避基值（秒）")


class FeatureToggles(BaseModel):
    """分析功能开关"""

    topic_enabled: bool = Field(default=True, description="启用话题分析")
    user_title_enabled: bool = Field(default=True, description="启用用户称号分析")
    golden_quote_enabled: bool = Field(default=True, description="启用金句分析")
    chat_quality_enabled: bool = Field(default=True, description="启用聊天质量锐评")
    max_topics: int = Field(default=5, description="最大话题数量")
    max_user_titles: int = Field(default=8, description="最大用户称号数量")
    max_golden_quotes: int = Field(default=5, description="最大金句数量")


class RenderSettings(BaseModel):
    """图片渲染配置"""

    report_template: str = Field(default="scrapbook", description="报告模板名称")
    profile_display_mode: str = Field(
        default="mbti", description="人格标签展示模式 (mbti/sbti/acgti)"
    )
    device_scale_factor: float = Field(default=1.8, description="渲染分辨率倍率")
    render_timeout: int = Field(default=50000, description="渲染超时时间（毫秒）")


class AutoAnalysisSettings(BaseModel):
    """定时分析配置"""

    enabled: bool = Field(
        default=False, description="启用定时分析功能（需通过命令订阅具体群聊）"
    )
    times: list[str] = Field(
        default=["23:00"],
        description="自动分析时间列表 (HH:MM)，订阅的群聊将在此时间段执行分析",
    )


class PluginConfig(BaseModel):
    """群日常分析插件主配置"""

    analysis_days: int = Field(default=1, description="默认分析天数")
    min_messages: int = Field(default=200, description="最小消息数阈值")
    output_format: str = Field(
        default="image", description="输出格式 (image/text/html)"
    )
    llm: LLMSettings = Field(default_factory=LLMSettings)
    features: FeatureToggles = Field(default_factory=FeatureToggles)
    render: RenderSettings = Field(default_factory=RenderSettings)
    auto_analysis: AutoAnalysisSettings = Field(default_factory=AutoAnalysisSettings)


class Config(BaseModel):
    """插件主配置（顶层嵌套）"""

    group_daily_analysis: PluginConfig = Field(
        default_factory=PluginConfig, description="群日常分析配置"
    )


config = get_plugin_config(Config).group_daily_analysis

TEMPLATE_DIR = Path(__file__).parent / "templates"
PROMPT_DIR = Path(__file__).parent / "prompts"
