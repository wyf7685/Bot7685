# ruff: noqa: N815
import dataclasses
import datetime
import functools
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..const import APP_NAME, VERSION


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


CARD_POOL_NAME: dict[CardPoolType, str] = {
    CardPoolType.CHARACTER: "角色活动唤取",
    CardPoolType.WEAPON: "武器活动唤取",
    CardPoolType.CHARACTER_PERMANENT: "角色常驻唤取",
    CardPoolType.WEAPON_PERMANENT: "武器常驻唤取",
    CardPoolType.BEGINNER: "新手唤取",
    CardPoolType.BEGINNER_SELECT: "新手自选唤取",
    CardPoolType.BEGINNER_SELECT_THANKSGIVING: "新手自选唤取（感恩定向唤取）",
}


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

    @functools.cached_property
    def timestamp(self) -> int:
        return int(datetime.datetime.fromisoformat(self.time).timestamp())


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
    export_app: str = APP_NAME
    export_app_version: str = VERSION
    wwgf_version: str = "v0.1b"
    region_time_zone: int = 8

    def update(self) -> None:
        self.export_timestamp = int(datetime.datetime.now().timestamp())


class WWGFItem(BaseModel):
    gacha_id: str
    """卡池 ID

    >>> f"{cardPoolType:04d}"
    """
    gacha_type: str
    """卡池类型(名称)

    >>> CARD_POOL_NAME[card_pool_type]
    """
    item_id: str
    """resourceId"""
    count: str
    time: str
    name: str
    item_type: str
    """resourceType"""
    rank_type: str
    """qualityLevel"""
    id: str
    """抽卡记录ID

    >>> f"{int(timestamp)}{gacha_id}{seq:05d}"
    """


@dataclasses.dataclass
class WWGFMergeStatistics:
    old: int = 0
    """旧的记录数"""
    common: int = 0
    """重复的记录数"""
    new: int = 0
    """新的记录数"""


class WWGF(BaseModel):
    """WutheringWaves Gachalog Format"""

    info: WWGFInfo
    list: list[WWGFItem]

    def sort(self) -> None:
        items = {f"{i.value:04d}": list[WWGFItem]() for i in CardPoolType}
        for item in self.list:
            items[item.gacha_id].append(item)

        self.list[:] = []
        for key in sorted(items.keys()):
            self.list.extend(items[key])

    def merge(self, other: WWGF) -> WWGFMergeStatistics:
        items = self.list[:]
        seen = {item.id for item in items}
        stats = WWGFMergeStatistics(old=len(seen))

        for item in other.list:
            if item.id in seen:
                stats.common += 1
            else:
                items.append(item)
                seen.add(item.id)
                stats.new += 1
        stats.old -= stats.common

        self.list[:] = items
        self.sort()
        self.info.update()
        return stats

    def dump(self, indent: int | None = None) -> str:
        self.info.update()
        return self.model_dump_json(indent=indent)

    def dump_file(self, file: Path) -> None:
        _ = file.write_text(self.dump(), encoding="utf-8")

    @property
    def size(self) -> int:
        return len(self.list)
