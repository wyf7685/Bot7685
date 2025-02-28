# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


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


@final
class WuwaSkinDataRequest(WebRequest[WuwaSkinData]):
    """鸣潮皮肤数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/skinData",
        method="POST",
    )
    _resp_ = WuwaSkinData

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
