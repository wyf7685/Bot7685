from pathlib import Path

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class AnalysisConfig(BaseModel):
    """分析相关配置"""

    top_n: int = Field(default=200, description="热词数量")
    min_freq: int = Field(default=1, description="最小词频")
    min_word_len: int = Field(default=1, description="词最小长度")
    max_word_len: int = Field(default=10, description="词最大长度")
    min_freq_threshold: int = Field(default=1, description="词频过滤阈值")
    contributor_top_n: int = Field(default=10, description="显示贡献者数量")
    sample_count: int = Field(default=10, description="每个词的样本数")


class NewWordDiscoveryConfig(BaseModel):
    """新词发现配置"""

    pmi_threshold: float = Field(default=2.0, description="PMI 阈值")
    entropy_threshold: float = Field(default=0.5, description="熵阈值")
    new_word_min_freq: int = Field(default=20, description="新词最小频率")


class WordMergeConfig(BaseModel):
    """词组合并配置"""

    merge_min_freq: int = Field(default=30, description="合并最小频率")
    merge_min_prob: float = Field(default=0.3, description="合并最小概率")
    merge_max_len: int = Field(default=6, description="合并词最大长度")


class SingleCharConfig(BaseModel):
    """单字过滤配置"""

    single_min_solo_ratio: float = Field(default=0.01, description="单字独立比例阈值")
    single_min_solo_count: int = Field(default=5, description="单字独立最小数量")


class FilterConfig(BaseModel):
    """过滤相关配置"""

    whitelist: set[str] = Field(default_factory=set, description="白名单")
    blacklist: set[str] = Field(default_factory=set, description="黑名单")
    stopwords: set[str] = Field(default_factory=set, description="停用词")
    filter_bot_messages: bool = Field(
        default=True, description="是否过滤 QQ 机器人消息"
    )


class TimeConfig(BaseModel):
    """时间相关配置"""

    night_owl_hours: set[int] = Field(
        default_factory=lambda: set(range(6)), description="深夜时段（小时）"
    )
    early_bird_hours: set[int] = Field(
        default_factory=lambda: set(range(6, 9)), description="早起时段（小时）"
    )


class OpenAIConfig(BaseModel):
    """OpenAI API 配置"""

    api_key: str = Field(description="API Key")
    base_url: str = Field(description="API 基础 URL")
    model: str = Field(description="模型名称")


class PluginConfig(BaseModel):
    """全局配置"""

    # 分析配置
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    # 新词发现配置
    new_word_discovery: NewWordDiscoveryConfig = Field(
        default_factory=NewWordDiscoveryConfig
    )
    # 词组合并配置
    word_merge: WordMergeConfig = Field(default_factory=WordMergeConfig)
    # 单字过滤配置
    single_char: SingleCharConfig = Field(default_factory=SingleCharConfig)
    # 过滤配置
    filter: FilterConfig = Field(default_factory=FilterConfig)
    # 时间配置
    time: TimeConfig = Field(default_factory=TimeConfig)
    # OpenAI 配置
    openai: OpenAIConfig = Field()


class Config(BaseModel):
    """插件主配置"""

    annual_report: PluginConfig = Field()


config = get_plugin_config(Config).annual_report
TEMPLATE_FILE = Path(__file__).parent / "templates" / "report_template.html.jinja2"
