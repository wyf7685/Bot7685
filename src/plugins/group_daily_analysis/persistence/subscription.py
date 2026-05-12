"""分析订阅管理 — 基于 ConfigListFile 持久化。"""

from copy import deepcopy
from typing import Any

from nonebot_plugin_alconna import MsgTarget, Target
from nonebot_plugin_localstore import get_plugin_data_file
from nonebot_plugin_uninfo import Session
from pydantic import BaseModel, Field

from src.utils import ConfigListFile


class AnalysisSubscription(BaseModel):
    """一条分析订阅记录"""

    target_data: dict[str, Any] = Field(description="MsgTarget.dump() 序列化数据")
    session_data: Session = Field(description="uninfo Session 对象，用于查询消息")
    analysis_days: int = Field(default=1, description="分析天数")
    incremental_enabled: bool = Field(default=False, description="是否使用增量分析模式")

    @property
    def target(self) -> Target:
        return Target.load(deepcopy(self.target_data))


# 全局订阅文件实例
subscriptions = ConfigListFile(
    get_plugin_data_file("subscriptions.json"),
    AnalysisSubscription,
)


def add_subscription(sub: AnalysisSubscription) -> None:
    """添加订阅，如果已存在则更新。"""
    # 去重：同一个 target 只保留一条
    subscriptions.save(
        [s for s in subscriptions.load() if not s.target.verify(sub.target)] + [sub]
    )


def remove_subscription(target: MsgTarget) -> bool:
    """移除当前会话的订阅。返回是否有移除。"""
    before = len(subscriptions.load())
    subscriptions.remove(lambda s: target.verify(s.target))
    return len(subscriptions.load()) < before


def list_subscriptions(target: MsgTarget | None = None) -> list[AnalysisSubscription]:
    """列出订阅。传入 target 时只返回匹配的。"""
    all_subs = subscriptions.load()
    if target is None:
        return all_subs
    return [s for s in all_subs if target.verify(s.target)]
