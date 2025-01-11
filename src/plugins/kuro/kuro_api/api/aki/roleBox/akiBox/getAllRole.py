# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class Role(ResponseData):
    acronym: str
    """角色名称音序"""
    attributeName: str
    """属性名称"""
    roleIconUrl: str
    roleId: int
    """角色 ID"""
    roleName: str
    """角色名"""
    starLevel: int
    """星级"""


WuwaGetAllRole = list[Role]


class WuwaGetAllRoleRequest(WebRequest[WuwaGetAllRole]):
    """鸣潮游戏角色数据"""

    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/getAllRole",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[WuwaGetAllRole]:
        return WuwaGetAllRole
