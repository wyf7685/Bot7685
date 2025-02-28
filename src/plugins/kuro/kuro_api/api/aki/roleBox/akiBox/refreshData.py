# ruff: noqa: N815

from typing import final

from .....const import GameId
from ....common import RequestInfo, WebRequest


@final
class WuwaRefreshDataRequest(WebRequest[bool]):
    """刷新数据 (?)"""

    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/refreshData",
        method="POST",
    )
    _resp_ = bool

    gameId: GameId
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1
