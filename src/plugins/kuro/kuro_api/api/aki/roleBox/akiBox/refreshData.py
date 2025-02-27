# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from .....common import RequestInfo, WebRequest
from .....const import GameId


@final
@dataclass
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
