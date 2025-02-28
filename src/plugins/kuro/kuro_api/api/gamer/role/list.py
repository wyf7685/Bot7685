# ruff: noqa: N815

from typing import ClassVar, final, override

from ....const import GameId, PnsGameId, WuwaGameId
from ...common import CommonRequestHeaders, Request, RequestInfo, ResponseData


class RoleListRequestHeaders(CommonRequestHeaders):
    @override
    def dump(self, *, without_distinct_id: bool = True) -> dict[str, str]:
        self.content_type: str = "application/x-www-form-urlencoded; charset=utf-8"
        return super().dump(without_distinct_id=without_distinct_id)


class BaseRole(ResponseData):
    userId: int
    serverId: str
    serverName: str
    roleId: str
    roleName: str
    isDefault: bool
    gameHeadUrl: str
    gameLevel: str
    roleNum: int


class PnsRole(BaseRole):
    gameId: PnsGameId
    roleScore: str
    fashionCollectionPercent: float


class WuwaRole(BaseRole):
    gameId: WuwaGameId
    phantomPercent: float
    achievementCount: int


type Role = PnsRole | WuwaRole


class BaseRoleListRequest[R: Role, T: GameId](Request[list[R]]):
    _info_: ClassVar[RequestInfo] = RequestInfo(
        url="https://api.kurobbs.com/gamer/role/list",
        method="POST",
    )

    gameId: T

    @override
    def create_headers(self, token: str) -> RoleListRequestHeaders:
        return RoleListRequestHeaders(token=token)


@final
class RoleListRequest(BaseRoleListRequest[Role, GameId]):
    """取账号绑定的游戏账号信息"""

    _resp_ = list[Role]


@final
class PnsRoleListRequest(BaseRoleListRequest[PnsRole, PnsGameId]):
    """取账号绑定的战双账号信息"""

    _resp_ = list[PnsRole]

    gameId: PnsGameId = GameId.PNS


@final
class WuwaRoleListRequest(BaseRoleListRequest[WuwaRole, WuwaGameId]):
    """取账号绑定的鸣潮账号信息"""

    _resp_ = list[WuwaRole]

    gameId: WuwaGameId = GameId.WUWA
