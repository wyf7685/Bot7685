# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from ....common import RequestInfo, WebRequest
from ....const import GameId


@final
@dataclass
class QueryUserIdRequest(WebRequest[int]):
    """查询用户 ID

    ? 用游戏角色数据反查库洛 UID 吗
    """

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/gamer/role/queryUserId",
        method="POST",
    )
    _resp_ = int

    gameId: GameId
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1
