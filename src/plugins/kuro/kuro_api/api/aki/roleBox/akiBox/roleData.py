# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest
from .getRoleDetail import Role as BaseRole
from .getRoleDetail import RoleSkin


class Role(BaseRole):
    roleSkin: RoleSkin


class WuwaRoleData(ResponseData):
    roleList: list[Role]
    """角色列表"""
    showRoleIdList: list[int]
    """展柜角色 ID"""
    showToGuest: bool


@final
class WuwaRoleDataRequest(WebRequest[WuwaRoleData]):
    """鸣潮游戏角色数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/roleData",
        method="POST",
    )
    _resp_ = WuwaRoleData

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
