# ruff: noqa: N815
import dataclasses
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class CardPoolType(int, Enum):
    CHARACTER = 1
    """角色活动唤取"""
    WEAPON = 2
    """武器活动唤取"""
    CHARACTER_PERMANENT = 3
    """角色常驻唤取"""
    WEAPON_PERMANENT = 4
    """武器常驻唤取"""
    BEGINNER = 5
    """新手唤取"""
    BEGINNER_SELECT = 6
    """新手自选唤取"""
    BEGINNER_SELECT_THANKSGIVING = 7
    """新手自选唤取（感恩定向唤取）"""


@dataclasses.dataclass
class GachaParams:
    cardPoolId: str
    cardPoolType: int
    languageCode: str
    playerId: str
    recordId: str
    serverId: str


class GachaItem(BaseModel):
    cardPoolType: str
    """卡池名称"""
    resourceId: int
    """物品 ID"""
    qualityLevel: int
    """星级"""
    resourceType: Literal["角色", "武器"]
    """物品类型"""
    name: str
    """物品名称"""
    count: int
    """数量"""
    time: str
    """时间"""


class GachaResponse(BaseModel):
    code: Literal[0]
    message: Literal["success"]
    data: list[GachaItem]


# WWGF (?)
# ref: https://github.com/TomyJan/Yunzai-Kuro-Plugin/blob/f68575e/model/mcGachaData.js#L336-L347


class WWGFInfo(BaseModel):
    uid: str
    lang: str = "zh-cn"
    export_timestamp: int
    export_app: str
    export_app_version: str
    wwgf_version: str = "v0.1b"
    region_time_zone: int = 8


class WWGFItem(BaseModel):
    gacha_id: str
    """卡池 ID

    >>> f"{cardPoolType:04d}"
    """
    gacha_type: str
    item_id: str
    count: str
    time: str
    name: str
    item_type: str
    """resourceId"""
    rank_type: str
    """qualityLevel"""
    id: str
    """抽卡记录ID

    >>> f"{int(timestamp)}{cardPoolType:04d}{seq:05d}"
    """


class WWGF(BaseModel):
    """WutheringWaves Gachalog Format"""

    info: WWGFInfo
    list: list[WWGFItem]

    def sort(self) -> None:
        self.list.sort(key=lambda item: (int(item.gacha_id), item.id), reverse=True)
