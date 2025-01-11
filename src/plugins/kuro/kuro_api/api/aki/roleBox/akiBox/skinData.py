# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class RoleSkin(ResponseData):
    acronym: str
    """皮肤名称音序"""
    isAddition: bool
    picUrl: str
    priority: int
    quality: int
    qualityName: str
    roleId: int
    """角色 ID"""
    roleName: str
    """角色名称"""
    skinIcon: str
    skinId: int
    skinName: str
    """皮肤名称"""


class WeaponSkin(ResponseData):
    isAddition: bool
    priority: int
    quality: int
    qualityName: str
    skinIcon: str
    skinId: int
    skinName: str
    weaponTypeIcon: str
    weaponTypeId: int
    weaponTypeName: str


class WuwaSkinData(ResponseData):
    roleSkinList: list[RoleSkin]
    weaponSkinList: list[WeaponSkin]
    showToGuest: bool


class WuwaSkinDataRequest(WebRequest[WuwaSkinData]):
    """鸣潮皮肤数据"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/skinData",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaSkinData]:
        return WuwaSkinData
