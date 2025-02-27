# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from pydantic import Field

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class Box(ResponseData):
    name: str
    num: int


class WuwaBaseData(ResponseData):
    achievementCount: int
    achievementStar: int
    activeDays: int
    bigCount: int
    # boxList: list[Box]
    chapterId: int
    createTime: int = Field(alias="creatTime")
    energy: int
    id: int
    level: int
    liveness: int
    livenessMaxCount: int
    livenessUnlock: bool
    maxEnergy: int
    name: str
    phantomBoxList: list[Box]
    """潮汐之遗"""
    roleNum: int
    showToGuest: bool
    smallCount: int
    storeEnergy: int
    storeEnergyIconUrl: str
    storeEnergyLimit: int
    storeEnergyTitle: str
    treasureBoxList: list[Box]
    """奇藏箱"""
    weeklyInstCount: int
    weeklyInstCountLimit: int
    weeklyInstIconUrl: str
    weeklyInstTitle: str
    worldLevel: int


@final
@dataclass
class WuwaBaseDataRequest(WebRequest[WuwaBaseData]):
    """鸣潮游戏角色基础数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/baseData",
        method="POST",
    )
    _resp_ = WuwaBaseData

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
