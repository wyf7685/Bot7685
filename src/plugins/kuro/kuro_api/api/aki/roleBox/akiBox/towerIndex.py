# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class Role(ResponseData):
    roleId: int
    """角色 ID

    使用 `roleData` 查询详细信息
    """
    iconUrl: str


class Floor(ResponseData):
    floor: int
    """塔内层数, 从 1 开始"""
    picUrl: str
    roleList: list[Role]
    """挑战当前层的角色列表"""
    star: int
    """当前层星数 [0,3]"""


class TowerArea(ResponseData):
    areaId: int
    """深塔区域内塔编号, 游戏内从左到右1-3(2)"""
    areaName: str
    """编号对应名称"""
    floorList: list[Floor]
    maxStar: int
    """当前塔最大星数"""
    star: int
    """当前塔总星数"""


class DifficultyItem(ResponseData):
    difficulty: int
    """深塔区域编号

    稳定区 = 1
    实验区 = 2
    深境区 = 3
    超载区 = 4
    """
    difficultyName: str
    """深塔区域名称"""
    towerAreaList: list[TowerArea]


class WuwaTower(ResponseData):
    difficultyList: list[DifficultyItem]
    isUnlock: bool
    seasonEndTime: int  # 1057304584 <==== ???


class WuwaTowerIndexRequest(WebRequest[WuwaTower]):
    """鸣潮逆境深塔数据概览"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/towerIndex",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaTower]:
        return WuwaTower
