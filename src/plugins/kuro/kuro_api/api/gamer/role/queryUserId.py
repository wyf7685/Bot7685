# ruff: noqa: N815

from typing import override

from ....common import RequestInfo, WebRequest
from ....const import GameId


class QueryUserIdRequest(WebRequest[int]):
    """查询用户 ID

    ? 用游戏角色数据反查库洛 UID 吗
    """

    gameId: GameId
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/gamer/role/queryUserId",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[int]:
        return int
