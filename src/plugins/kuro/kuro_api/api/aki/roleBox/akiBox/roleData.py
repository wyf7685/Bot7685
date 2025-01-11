# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId
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


class WuwaRoleDataRequest(WebRequest[WuwaRoleData]):
    """鸣潮游戏角色数据"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/roleData",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaRoleData]:
        return WuwaRoleData
