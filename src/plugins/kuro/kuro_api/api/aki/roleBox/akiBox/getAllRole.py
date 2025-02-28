# ruff: noqa: N815

from typing import final

from .....const import GameId, WuwaGameId
from ....common import RequestInfo, ResponseData, WebRequest


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


@final
class WuwaGetAllRoleRequest(WebRequest[WuwaGetAllRole]):
    """鸣潮游戏角色数据"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/getAllRole",
        method="POST",
    )
    _resp_ = WuwaGetAllRole

    roleId: str
    serverId: str
    gameId: WuwaGameId = GameId.WUWA
