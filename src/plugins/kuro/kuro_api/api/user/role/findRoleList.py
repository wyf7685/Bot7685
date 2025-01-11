# ruff: noqa: N815

from typing import override

from ....common import CommonRequestHeaders, Request, RequestInfo, ResponseData
from ....const import GameId


class FindRoleListRequestHeaders(CommonRequestHeaders):
    @override
    def dump(self, *, without_distinct_id: bool = True) -> dict[str, str]:
        self.content_type: str = "application/x-www-form-urlencoded; charset=utf-8"
        return super().dump(without_distinct_id=without_distinct_id)


class Role(ResponseData):
    bindStatus: int
    """绑定状态"""
    createTime: int
    """绑定时间戳"""
    gameId: GameId
    """游戏 ID"""
    isDefault: bool
    """是否默认展示账号"""
    isHidden: bool
    roleId: str
    """角色 ID"""
    roleName: str
    """角色昵称"""
    serverId: str
    """服务器 ID"""
    serverName: str
    """服务器名称"""
    userId: str
    """库洛 UID"""

FindRoleList = list[Role]

class FindRoleListRequest(Request[FindRoleList]):
    """取绑定游戏账号列表"""

    gameId: GameId

    @override
    def create_headers(self, token: str) -> FindRoleListRequestHeaders:
        return FindRoleListRequestHeaders(token=token)

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/user/role/findRoleList",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[FindRoleList]:
        return FindRoleList
